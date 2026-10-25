"""Transparent, conservative eligibility grammar; entity matches are not rules.

Only complete criteria in a small documented grammar become executable. Anything
outside that grammar is retained verbatim for review, including temporal wording.
No model predictions or country-specific thresholds enter this module.
"""
from __future__ import annotations

import re
import time
import unicodedata
import math
from typing import Any

NUMBER = r"\d+(?:\.\d+)?"
FIELDS = {
    "age": r"(?:age(?:d)?|ages)",
    "bmi": r"(?:bmi|body mass index)(?:\s*\(bmi\))?",
    "hba1c": r"(?:hba1c|hb a1c|a1c|glycated hemoglobin|glycosylated hemoglobin)(?:\s*\(hba1c\))?",
    "systolic_bp": r"(?:systolic blood pressure|systolic bp|sbp)",
    "diastolic_bp": r"(?:diastolic blood pressure|diastolic bp|dbp)",
}
CONDITIONS = {
    "type_2_diabetes": r"(?:type[ -]?2 diabetes(?: mellitus)?|t2dm|t2d)",
    "type_1_diabetes": r"(?:type[ -]?1 diabetes(?: mellitus)?|t1dm|t1d)",
    "severe_renal_impairment": r"(?:severe renal impairment)",
    "severe_kidney_disease": r"(?:severe kidney disease)",
    "pregnant": r"(?:pregnant|pregnancy)",
    "hypertension": r"(?:hypertension)",
}
CANONICAL_UNITS = {
    "age": "years", "bmi": "kg/m2", "hba1c": "%",
    "systolic_bp": "mmHg", "diastolic_bp": "mmHg",
}
UNITS = r"(?:years?|yrs?|months?|mos?|kg\s*/\s*m(?:\^?2)|kg\s*\.\s*m-2|%|percent|mmol\s*/\s*mol|mm\s*hg|kpa)"
COMPARATORS = {
    ">=": "gte", "at least": "gte", "greater than or equal to": "gte",
    "greater than or equal": "gte", "no less than": "gte", "not less than": "gte",
    "<=": "lte", "at most": "lte", "less than or equal to": "lte",
    "less than or equal": "lte", "no more than": "lte", "not more than": "lte",
    ">": "gt", "greater than": "gt", "more than": "gt", "above": "gt", "over": "gt",
    "<": "lt", "less than": "lt", "below": "lt", "under": "lt",
    "=": "equals", "equal to": "equals", "equals": "equals",
}
COMP_PATTERN = "(?:" + "|".join(re.escape(x) for x in sorted(COMPARATORS, key=len, reverse=True)) + ")"
TEMPORAL = re.compile(r"\b(?:within|previous|past|prior|last|during|before|after|since|duration|for\s+(?:at least\s+)?\d|screening|baseline|visit|stable|history of)\b", re.I)
AMBIGUOUS = re.compile(r"\b(?:approximately|about|around|unless|except|if|as determined|investigator|clinically significant|adequate|uncontrolled|and/or)\b", re.I)
NEGATION = re.compile(r"\b(?:no|not|without|absence|absent|negative)\b", re.I)


def normalize_with_offsets(text: str) -> tuple[str, list[int]]:
    """NFKC with an index map back to the original input (end-exclusive spans)."""
    normalized: list[str] = []
    offsets: list[int] = []
    replacements = {"≤": "<=", "≥": ">=", "−": "-", "–": "-", "—": "-", "\u00a0": " "}
    for index, character in enumerate(text):
        value = unicodedata.normalize("NFKC", character)
        value = "".join(replacements.get(x, x) for x in value)
        normalized.extend(value)
        offsets.extend([index] * len(value))
    return "".join(normalized), offsets


def normalize_text(text: str) -> str:
    return normalize_with_offsets(text)[0]


def tokenize(text: str) -> list[dict[str, Any]]:
    """Offset-preserving tokenizer. Negation and connective words are retained."""
    return [{"text": match.group(), "start": match.start(), "end": match.end()}
            for match in re.finditer(r"\d+(?:\.\d+)?|[\w]+(?:[-'][\w]+)*|<=|>=|[^\w\s]", text)]


def convert_measurement(field: str, value: float, unit: str | None) -> tuple[float, str]:
    """Convert supported units; never guess an unknown unit.

    Absent units use the field's documented canonical input convention. A unit
    explicitly given in source or profile must be supported for that field.
    """
    canonical = CANONICAL_UNITS[field]
    if not math.isfinite(float(value)):
        raise ValueError("Measurement must be finite.")
    normalized = re.sub(r"\s+", "", normalize_text(unit or canonical)).casefold()
    if field == "age":
        if normalized in {"year", "years", "yr", "yrs"}:
            return float(value), canonical
        if normalized in {"month", "months", "mo", "mos"}:
            return float(value) / 12, canonical
    elif field == "bmi" and normalized in {"kg/m2", "kg/m^2", "kg.m-2"}:
        return float(value), canonical
    elif field == "hba1c":
        if normalized in {"%", "percent"}:
            return float(value), canonical
        if normalized == "mmol/mol":
            # NGSP's IFCC -> NGSP master equation; see docs/rule_semantics.md.
            return 0.09148 * float(value) + 2.152, canonical
    elif field in {"systolic_bp", "diastolic_bp"}:
        if normalized == "mmhg":
            return float(value), canonical
        if normalized == "kpa":
            converted = float(value) * (1000 / 133.322387415)
            if not math.isfinite(converted):
                raise ValueError("Converted measurement must be finite.")
            return converted, canonical
    raise ValueError(f"Unsupported {field} unit: {unit}")


def _source(normalized_start: int, normalized_end: int, offsets: list[int], original: str, study_id: str | None) -> dict[str, Any]:
    start = offsets[normalized_start] if normalized_start < len(offsets) else len(original)
    end = offsets[normalized_end - 1] + 1 if normalized_end > normalized_start else start
    return {"source_text": original[start:end], "source_start": start, "source_end": end, "study_id": study_id}


def _segments(text: str) -> list[tuple[str, int, int, str]]:
    """Group wrapped bullet/paragraph lines; section boundaries carry scope.

    Sentence boundaries are deliberately not used to execute fragments of one
    bullet. An unsupported exception in its next sentence invalidates the whole
    bullet. Distinct paragraphs and bullets are separate conjunctive criteria.
    """
    result: list[tuple[str, int, int, str]] = []
    section = "inclusion"
    pending_start: int | None = None
    pending_end = 0
    pending_indent: int | None = None

    def flush() -> None:
        nonlocal pending_start, pending_indent
        if pending_start is not None:
            result.append((text[pending_start:pending_end], pending_start, pending_end, section))
        pending_start = None
        pending_indent = None

    for line in re.finditer(r"[^\n]*(?:\n|$)", text):
        if line.start() == line.end():
            continue
        raw = line.group().rstrip("\r\n")
        if not raw.strip():
            flush()
            continue
        offset = line.start() + len(raw) - len(raw.lstrip())
        content = raw.strip()
        header = re.match(r"(?:key\s+)?(inclusion|exclusion)\b\s*(?:criteria\b)?\s*[:\-]?\s*", content, re.I)
        if header:
            flush()
            section = header.group(1).lower()
            offset += header.end()
            content = content[header.end():]
        bullet = re.match(r"(?:[-*•]\s+|\(?\d+\)?[.)]\s+)", content)
        if bullet:
            current_indent = offset - line.start()
            if pending_start is not None and pending_indent is not None and current_indent > pending_indent:
                # Nested bullets may qualify their parent. Preserve as a whole
                # criterion rather than detaching apparently executable leaves.
                pending_end = offset + len(content)
                continue
            flush()
            pending_indent = current_indent
            offset += bullet.end()
            content = content[bullet.end():]
        if not content:
            continue
        if pending_start is None:
            pending_start = offset
        pending_end = offset + len(content)
    flush()
    return result


def segment_sentences(text: str) -> list[dict[str, Any]]:
    """Display-oriented segmentation, independent of safe rule boundaries."""
    spans = []
    for match in re.finditer(r"[^\n;]+", text):
        start = match.start()
        for boundary in re.finditer(r"(?<=[.!?])\s+(?=[A-Z])", match.group()):
            end = match.start() + boundary.start()
            if text[start:end].strip():
                spans.append({"text": text[start:end], "start": start, "end": end})
            start = match.start() + boundary.end()
        if text[start:match.end()].strip():
            spans.append({"text": text[start:match.end()], "start": start, "end": match.end()})
    return spans


def _leaf(field: str, operator: str, **values: Any) -> dict[str, Any]:
    return {"kind": "condition", "field": field, "operator": operator, **values}


def _group(logic: str, children: list[dict[str, Any]]) -> dict[str, Any]:
    return {"kind": "group", "logic": logic, "children": children}


def _cleanup(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip().rstrip(".").strip()
    text = re.sub(r"^(?:participants?|patients?|subjects?|individuals?)\s+", "", text, flags=re.I)
    text = re.sub(r"^(?:must|shall)\s+", "", text, flags=re.I)
    return text


def _numeric(field: str, expression: str) -> dict[str, Any] | None:
    expression = expression.strip()
    expression = re.sub(r"^(?:(?:must|shall)\s+be|is|of|:)\s*", "", expression, flags=re.I)
    expression = re.sub(r"\s+(?:of age|old)$", "", expression, flags=re.I)
    # A whole expression consists only of a range/comparison plus a known unit.
    unit_match = re.search(rf"\s*({UNITS})\s*$", expression, re.I)
    unit = unit_match.group(1) if unit_match else None
    if unit_match:
        expression = expression[:unit_match.start()].strip()
    # HbA1c and pressure have incompatible common unit scales. A bare number
    # must not silently be interpreted as a percentage or mmHg.
    if field in {"hba1c", "systolic_bp", "diastolic_bp"} and unit is None:
        suffix = re.fullmatch(r"(.+)\s+(inclusive|exclusive)", expression, re.I)
        if suffix and re.search(UNITS + r"\s*$", suffix.group(1), re.I):
            parsed = _numeric(field, suffix.group(1))
            if parsed and parsed["operator"].startswith("between_"):
                exclusive = suffix.group(2).lower() == "exclusive"
                parsed.update(operator="between_exclusive" if exclusive else "between_inclusive",
                              lower_inclusive=not exclusive, upper_inclusive=not exclusive)
                return parsed
        return None
    try:
        convert_measurement(field, 1, unit)
    except ValueError:
        return None

    def value(number: str, explicit_unit: str | None = None) -> float:
        return convert_measurement(field, float(number), explicit_unit or unit)[0]

    bounds = re.fullmatch(rf"(?:between\s+|from\s+)?({NUMBER})\s*(?:({UNITS})\s*)?(?:and|to|-)\s*({NUMBER})(?:\s+(inclusive|exclusive))?", expression, re.I)
    if bounds:
        if bounds.group(2) and unit is None:
            return None
        lower, upper = value(bounds.group(1), bounds.group(2)), value(bounds.group(3))
        exclusive = (bounds.group(4) or "").lower() == "exclusive"
        return _leaf(field, "between_exclusive" if exclusive else "between_inclusive",
                     lower=lower, upper=upper, unit=CANONICAL_UNITS[field],
                     lower_inclusive=not exclusive, upper_inclusive=not exclusive,
                     unit_assumed=unit is None)
    # Also accept an explicit suffix after the unit: age between 18 and 65 years exclusive.
    suffix = re.fullmatch(r"(.+)\s+(inclusive|exclusive)", expression, re.I)
    if suffix and re.search(UNITS + r"\s*$", suffix.group(1), re.I):
        parsed = _numeric(field, suffix.group(1))
        if parsed and parsed["operator"].startswith("between_"):
            exclusive = suffix.group(2).lower() == "exclusive"
            parsed.update(operator="between_exclusive" if exclusive else "between_inclusive",
                          lower_inclusive=not exclusive, upper_inclusive=not exclusive)
            return parsed
    comparison = re.fullmatch(rf"({COMP_PATTERN})\s*({NUMBER})", expression, re.I)
    if comparison:
        return _leaf(field, COMPARATORS[comparison.group(1).lower()], value=value(comparison.group(2)),
                     unit=CANONICAL_UNITS[field], unit_assumed=unit is None)
    trailing = re.fullmatch(rf"({NUMBER})\s*(?:({UNITS})\s*)?(and older|or older|and above|or above|and younger|or younger|or less|and below)", expression, re.I)
    if trailing:
        operator = "gte" if trailing.group(3).lower() in {"and older", "or older", "and above", "or above"} else "lte"
        return _leaf(field, operator, value=value(trailing.group(1), trailing.group(2)),
                     unit=CANONICAL_UNITS[field], unit_assumed=unit is None and trailing.group(2) is None)
    # Two explicit comparisons on the same field. No unit/qualifier is discarded.
    combined = re.fullmatch(rf"({COMP_PATTERN})\s*({NUMBER})\s*(?:({UNITS})\s*)?(?:and|,)\s*({COMP_PATTERN})\s*({NUMBER})", expression, re.I)
    if combined:
        return _group("AND", [
            _leaf(field, COMPARATORS[combined.group(1).lower()], value=value(combined.group(2), combined.group(3)), unit=CANONICAL_UNITS[field], unit_assumed=unit is None and combined.group(3) is None),
            _leaf(field, COMPARATORS[combined.group(4).lower()], value=value(combined.group(5)), unit=CANONICAL_UNITS[field], unit_assumed=unit is None),
        ])
    return None


def _atom(text: str) -> dict[str, Any] | None:
    text = _cleanup(text)
    for field, pattern in FIELDS.items():
        chained = re.fullmatch(rf"({NUMBER})\s*(<|<=|>|>=)\s*{pattern}\s*(<|<=|>|>=)\s*({NUMBER})\s*({UNITS})?", text, re.I)
        if chained:
            unit = chained.group(5)
            if unit is None and field in {"hba1c", "systolic_bp", "diastolic_bp"}:
                return None
            try:
                left, canonical = convert_measurement(field, float(chained.group(1)), unit)
                right, _ = convert_measurement(field, float(chained.group(4)), unit)
            except ValueError:
                return None
            inverse = {"<": "gt", "<=": "gte", ">": "lt", ">=": "lte"}
            return _group("AND", [_leaf(field, inverse[chained.group(2)], value=left, unit=canonical, unit_assumed=unit is None),
                                   _leaf(field, COMPARATORS[chained.group(3)], value=right, unit=canonical, unit_assumed=unit is None)])
        match = re.fullmatch(rf"{pattern}\s*(.+)", text, re.I)
        if match:
            result = _numeric(field, match.group(1))
            if result:
                return result
    age = re.fullmatch(r"(?:be\s+)?(.+?)\s+(?:years?\s+(?:of age|old))", text, re.I)
    if age:
        return _numeric("age", age.group(1) + " years")
    for field, pattern in CONDITIONS.items():
        negative = re.fullmatch(rf"(?:not\s+(?:have|be)|must\s+not\s+(?:have|be)|no|without|absence of|negative for)\s+{pattern}", text, re.I)
        positive = re.fullmatch(rf"(?:(?:have|has|with|be|diagnosed with|diagnosis of|a diagnosis of)\s+)?{pattern}", text, re.I)
        if negative or positive:
            return _leaf(field, "equals", value=not bool(negative), unit=None,
                         negated=bool(negative))
    return None


def _split_logic(text: str) -> tuple[list[str], list[str]] | None:
    """Split top-level AND/OR, protect between-ranges and comparator phrases."""
    protected: set[int] = set()
    for match in re.finditer(rf"\bbetween\s+{NUMBER}(?:\s*{UNITS})?\s+(and)\s+{NUMBER}|\b(?:greater|less)\s+than\s+(or)\s+equal|\b{NUMBER}(?:\s*{UNITS})?\s+(or|and)\s+(?:older|younger|above|below|less)\b", text, re.I):
        for group in range(1, 4):
            if match.start(group) >= 0:
                protected.add(match.start(group))
    depth = 0
    positions = []
    for match in re.finditer(r"\(|\)|\b(?:and|or)\b", text, re.I):
        token = match.group().lower()
        if token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
            if depth < 0:
                return None
        elif depth == 0 and match.start() not in protected:
            positions.append(match)
    if depth != 0:
        return None
    pieces = []
    operators = []
    start = 0
    for match in positions:
        pieces.append(text[start:match.start()].strip())
        operators.append(match.group().upper())
        start = match.end()
    pieces.append(text[start:].strip())
    return pieces, operators


def _expression(text: str, depth: int = 0) -> dict[str, Any] | None:
    if depth > 12:
        return None
    text = _cleanup(text)
    direct = _atom(text)
    if direct:
        return direct
    if text.startswith("(") and text.endswith(")"):
        # Only remove a pair enclosing the whole expression.
        nesting = 0
        closes_at_end = True
        for ix, character in enumerate(text):
            nesting += (character == "(") - (character == ")")
            if nesting == 0 and ix != len(text) - 1:
                closes_at_end = False
                break
        if closes_at_end:
            return _expression(text[1:-1], depth + 1)
    split = _split_logic(text)
    if not split:
        return None
    pieces, operators = split
    if not operators:
        return None
    # Mixed unparenthesized operators are ambiguous in protocol prose: abstain.
    if len(set(operators)) != 1:
        return None
    # "No diabetes or hypertension" can negate both conditions. Require
    # explicit scope instead of treating the second bare diagnosis as positive.
    if NEGATION.search(pieces[0]):
        for piece in pieces[1:]:
            if any(re.fullmatch(pattern, piece, re.I) for pattern in CONDITIONS.values()):
                return None
    parsed = [_expression(piece, depth + 1) for piece in pieces]
    if any(piece is None for piece in parsed):
        return None
    return _group(operators[0], parsed)


def _annotate(rule: dict[str, Any], source: dict[str, Any], section: str, rule_id: str) -> None:
    rule.update(source, id=rule_id, validated=True, validation_basis="supported_grammar",
                type="exclusion_constraint" if section == "exclusion" or rule.get("negated") else "inclusion")
    for index, child in enumerate(rule.get("children", [])):
        _annotate(child, source, section, f"{rule_id}.{index + 1}")


def extract(text: str, study_id: str | None = None) -> dict[str, Any]:
    """Extract display entities and fully covered, supported rule expressions."""
    started = time.perf_counter()
    normalized, offsets = normalize_with_offsets(text)
    entities = []
    for field, pattern in {**FIELDS, **CONDITIONS}.items():
        for match in re.finditer(rf"(?<!\w){pattern}(?!\w)", normalized, re.I):
            context = normalized[max(0, match.start() - 50):match.start()]
            context = re.split(r"[.;\n]|\band\b|\bor\b", context, flags=re.I)[-1]
            entities.append({"label": "measurement" if field in FIELDS else "condition", "field": field,
                             "text": text[offsets[match.start()]:offsets[match.end() - 1] + 1],
                             "negated": bool(NEGATION.search(context)),
                             **_source(match.start(), match.end(), offsets, text, study_id)})
    for match in re.finditer(rf"(?<![\w.]){NUMBER}(?:\s*{UNITS})?(?![\w.])", normalized, re.I):
        entities.append({"label": "quantity", "text": match.group(),
                         **_source(match.start(), match.end(), offsets, text, study_id)})
    entities.sort(key=lambda entity: (entity["source_start"], entity["source_end"]))
    rules, unresolved = [], []
    segments = _segments(normalized)
    # Unparsed list introductions can change scope of every listed item (OR,
    # exceptions, conditional subgroups). Do not execute their children as AND.
    scoped_sections = {
        section for criterion, _, _, section in segments
        if criterion.rstrip().endswith(":")
        or re.search(r"\b(?:any of|one of|either|following|at least one)\b", criterion, re.I)
    }
    for number, (criterion, start, end, section) in enumerate(segments, 1):
        source = _source(start, end, offsets, text, study_id)
        reason = None
        if section in scoped_sections:
            reason = "This section contains an unresolved list or conditional scope; its listed items require joint review."
        elif TEMPORAL.search(criterion):
            reason = "Temporal, historical, stability or visit qualification requires review."
        elif AMBIGUOUS.search(criterion):
            reason = "Conditional, ambiguous or investigator-dependent wording requires review."
        try:
            parsed = None if reason else _expression(criterion)
        except (ValueError, OverflowError):
            parsed = None
            reason = "Malformed or incompatible measurement units require review."
        if parsed is None:
            unresolved.append({**source, "type": section, "status": "NEEDS_REVIEW",
                               "reason": reason or "The entire criterion is not covered by the supported grammar; no fragment was executed."})
            continue
        if section == "exclusion":
            parsed = _group("NOT", [parsed])
        _annotate(parsed, source, section, f"rule-{number}")
        rules.append(parsed)
    from .eligibility import detect_contradictions
    contradictions = detect_contradictions(rules)
    return {
        "study_id": study_id, "normalized_text": normalized,
        "entities": entities, "rules": rules, "unresolved": unresolved,
        "contradictions": contradictions,
        "requires_human_validation": bool(unresolved or contradictions or not rules),
        "real_world_review_required": True,
        "stats": {"criterion_count": len(segments), "parsed_count": len(rules),
                  "unresolved_count": len(unresolved), "entity_count": len(entities),
                  "latency_ms": (time.perf_counter() - started) * 1000},
        "preprocessing": {"tokens": tokenize(normalized), "sentences": segment_sentences(normalized),
                          "clauses": [{"text": part, "start": start, "end": end, "section": section} for part, start, end, section in segments],
                          "negation_preserved": True, "method": "NFKC + offset tokenizer + full-clause grammar"},
        "parser_version": "conservative-grammar-v1",
    }
