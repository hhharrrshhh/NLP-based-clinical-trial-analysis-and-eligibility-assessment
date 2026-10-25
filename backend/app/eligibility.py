"""Three-valued comparison of synthetic profiles with source-grounded rules."""
from __future__ import annotations

import math
from typing import Any

TRUE, FALSE, UNKNOWN = "TRUE", "FALSE", "UNKNOWN"
ALIASES = {
    "age": ["age_years"], "bmi": ["bmi_kg_m2"], "hba1c": ["hba1c_percent"],
    "type_2_diabetes": ["reported_type2_diabetes"],
    "severe_kidney_disease": ["reported_severe_kidney_disease"],
}


def _and(values: list[str]) -> str:
    return FALSE if FALSE in values else UNKNOWN if UNKNOWN in values or not values else TRUE


def _or(values: list[str]) -> str:
    return TRUE if TRUE in values else UNKNOWN if UNKNOWN in values or not values else FALSE


def _not(value: str) -> str:
    return {TRUE: FALSE, FALSE: TRUE, UNKNOWN: UNKNOWN}[value]


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _profile_value(profile: dict[str, Any], field: str) -> Any:
    if field in profile:
        return profile[field]
    for alias in ALIASES.get(field, []):
        if alias in profile:
            return profile[alias]
    # Absence from a positive diagnoses list is NOT evidence of absence.
    conditions = profile.get("conditions")
    if isinstance(conditions, dict):
        return conditions.get(field)
    if isinstance(conditions, list) and field in conditions:
        return True
    return None


def _evaluate(rule: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    evidence = {key: rule.get(key) for key in ("study_id", "source_text", "source_start", "source_end")}
    result = {"rule_id": rule.get("id"), "rule": rule, "evidence": evidence,
              "normalized_condition": {key: rule[key] for key in ("field", "operator", "value", "lower", "upper", "unit", "logic") if key in rule}}
    if rule.get("validated") is not True:
        return {**result, "result": UNKNOWN, "patient_value": None, "explanation": "Rule is not validated against the supported grammar or explicit metadata."}
    if rule.get("kind") == "group" or "logic" in rule:
        children = [_evaluate(child, profile) for child in rule.get("children", [])]
        states = [child["result"] for child in children]
        logic = rule.get("logic")
        if logic == "AND":
            state = _and(states)
        elif logic == "OR":
            state = _or(states)
        elif logic == "NOT" and len(states) == 1:
            state = _not(states[0])
        else:
            state = UNKNOWN
        return {**result, "result": state, "children": children, "patient_value": None,
                "explanation": f"{logic} uses three-valued logic on child results {states}: {state}."}
    field = rule.get("field")
    actual = _profile_value(profile, field)
    result["patient_value"] = actual
    if actual is None:
        return {**result, "result": UNKNOWN, "explanation": f"{field} is missing; absence of information is not a negative finding."}
    expected = rule.get("value")
    operator = rule.get("operator")
    unit = rule.get("unit")
    if isinstance(expected, bool):
        if operator != "equals" or not isinstance(actual, bool):
            return {**result, "result": UNKNOWN, "explanation": f"{field} requires an explicit true/false observation."}
        passed = actual is expected
    elif isinstance(expected, str) and operator == "equals":
        if not isinstance(actual, str):
            return {**result, "result": UNKNOWN, "explanation": f"{field} requires a categorical string."}
        passed = actual.casefold() == expected.casefold()
    else:
        from .nlp import CANONICAL_UNITS, convert_measurement
        actual_unit = None
        if isinstance(actual, dict):
            actual_unit = actual.get("unit")
            actual = actual.get("value")
        if not _number(actual):
            return {**result, "result": UNKNOWN, "explanation": f"{field} is missing or is not a finite numerical measurement."}
        try:
            if field in CANONICAL_UNITS:
                actual, canonical_unit = convert_measurement(field, actual, actual_unit)
                if unit is not None and unit != canonical_unit:
                    return {**result, "result": UNKNOWN, "explanation": "Rule threshold is not in the declared canonical unit."}
            elif actual_unit:
                return {**result, "result": UNKNOWN, "explanation": "No unit conversion is registered for this field."}
        except ValueError as error:
            return {**result, "result": UNKNOWN, "explanation": str(error)}
        result["normalized_patient_value"] = actual
        if operator in {"gt", "gte", "lt", "lte", "equals"} and _number(expected):
            passed = {"gt": actual > expected, "gte": actual >= expected,
                      "lt": actual < expected, "lte": actual <= expected,
                      "equals": math.isclose(actual, expected, rel_tol=0, abs_tol=1e-10)}[operator]
        elif operator in {"range", "between_inclusive", "between_exclusive"} and _number(rule.get("lower")) and _number(rule.get("upper")):
            lower_inc = rule.get("lower_inclusive", operator != "between_exclusive")
            upper_inc = rule.get("upper_inclusive", operator != "between_exclusive")
            lower_ok = actual >= rule["lower"] if lower_inc else actual > rule["lower"]
            upper_ok = actual <= rule["upper"] if upper_inc else actual < rule["upper"]
            passed = lower_ok and upper_ok
        else:
            return {**result, "result": UNKNOWN, "explanation": "Unsupported operator or malformed threshold; rule was not executed."}
    expected_text = f"{rule.get('lower')} to {rule.get('upper')}" if "lower" in rule else str(expected)
    return {**result, "result": TRUE if passed else FALSE,
            "explanation": f"Observed {field}={actual}; source requires {operator} {expected_text} {unit or ''}. {'Matches' if passed else 'Does not match'} this known constraint."}


def _conjunctive_leaves(rule: dict[str, Any], negated: bool = False) -> list[dict[str, Any]]:
    if rule.get("validated") is not True:
        return []
    logic = rule.get("logic")
    if logic == "NOT" and len(rule.get("children", [])) == 1:
        return _conjunctive_leaves(rule["children"][0], not negated)
    if (logic == "AND" and not negated) or (logic == "OR" and negated):
        return [leaf for child in rule.get("children", []) for leaf in _conjunctive_leaves(child, negated)]
    if logic is not None:
        return []
    leaf = dict(rule)
    if negated:
        inverses = {"gt": "lte", "gte": "lt", "lt": "gte", "lte": "gt"}
        if leaf.get("operator") in inverses:
            leaf["operator"] = inverses[leaf["operator"]]
        elif leaf.get("operator") == "equals" and isinstance(leaf.get("value"), bool):
            leaf["value"] = not leaf["value"]
        else:
            return []
    return [leaf]


def detect_contradictions(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prove conflicts in unconditional conjunctive atoms, never guess OR SAT.

    This is not a general satisfiability solver. Only explicit comparable
    canonical-unit intervals and categorical equalities can be flagged.
    """
    fields: dict[str, dict[str, Any]] = {}
    contradictions = []
    for rule in rules:
        for leaf in _conjunctive_leaves(rule):
            field = leaf.get("field")
            if not field:
                continue
            state = fields.setdefault(field, {"lower": -math.inf, "upper": math.inf,
                                             "lower_inc": True, "upper_inc": True,
                                             "categories": [], "ids": []})
            state["ids"].append(leaf.get("id"))
            operator = leaf.get("operator")
            value = leaf.get("value")
            lower = upper = None
            lower_inc = upper_inc = True
            if operator == "equals" and isinstance(value, (bool, str)):
                if value not in state["categories"]:
                    state["categories"].append(value)
            elif _number(value):
                if operator in {"gt", "gte", "equals"}:
                    lower, lower_inc = value, operator != "gt"
                if operator in {"lt", "lte", "equals"}:
                    upper, upper_inc = value, operator != "lt"
            elif operator in {"range", "between_inclusive", "between_exclusive"}:
                lower, upper = leaf.get("lower"), leaf.get("upper")
                lower_inc = leaf.get("lower_inclusive", operator != "between_exclusive")
                upper_inc = leaf.get("upper_inclusive", operator != "between_exclusive")
            if _number(lower) and lower >= state["lower"]:
                state["lower_inc"] = lower_inc and (state["lower_inc"] if lower == state["lower"] else True)
                state["lower"] = lower
            if _number(upper) and upper <= state["upper"]:
                state["upper_inc"] = upper_inc and (state["upper_inc"] if upper == state["upper"] else True)
                state["upper"] = upper
    for field, state in fields.items():
        numeric_conflict = state["lower"] > state["upper"] or (state["lower"] == state["upper"] and not (state["lower_inc"] and state["upper_inc"]))
        if numeric_conflict or len(state["categories"]) > 1:
            contradictions.append({"field": field, "rule_ids": state["ids"],
                                   "reason": "The supported unconditional constraints for this field cannot all be satisfied."})
    return contradictions


def evaluate_profile(profile: dict[str, Any], rules: list[dict[str, Any]], unresolved: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Only synthetic profiles are accepted, and no result claims eligibility."""
    if profile.get("is_synthetic") is not True:
        raise ValueError("Synthetic evaluation requires is_synthetic=true. Real patient profiles are not supported.")
    unresolved = list(unresolved or [])
    evaluated = [_evaluate(rule, profile) for rule in rules]
    contradictions = detect_contradictions(rules)
    states = [result["result"] for result in evaluated]
    if contradictions:
        status = "INSUFFICIENT_INFORMATION"
        explanation = "Conflicting parsed criteria require protocol review before a profile conclusion."
    elif FALSE in states:
        status = "DOES_NOT_MATCH_KNOWN_CRITERIA"
        explanation = "At least one fully parsed known constraint is false; unresolved requirements are still reported."
    elif not states or UNKNOWN in states or unresolved:
        status = "INSUFFICIENT_INFORMATION"
        explanation = "Missing measurements, unsupported criteria or an empty rule set prevent a complete known-criteria match."
    else:
        status = "MATCHES_KNOWN_CRITERIA"
        explanation = "All supplied supported constraints match. This does not establish full study eligibility."
    return {"profile_id": profile.get("patient_id", profile.get("id")), "status": status,
            "rule_results": evaluated, "unresolved": unresolved, "contradictions": contradictions,
            "explanation": explanation, "is_synthetic": True, "real_world_review_required": True,
            "counts": {"true": states.count(TRUE), "false": states.count(FALSE), "unknown": states.count(UNKNOWN), "unresolved": len(unresolved)}}
