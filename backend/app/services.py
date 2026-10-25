"""Study-specific extraction, comparison and review-gated synthetic evaluation."""
import copy
import hashlib
import json
import re
from collections import Counter
from functools import lru_cache
from .config import NOTICE
from .nlp import extract, convert_measurement
from .eligibility import evaluate_profile, detect_contradictions
from .store import get_studies, get_study
from .reviews import get_reviews


def require_study(study_id):
    study = get_study(study_id)
    if study is None:
        raise KeyError(study_id)
    return study


@lru_cache(maxsize=256)
def _extract_cached(text, study_id, metadata_json):
    parsed = extract(text, study_id)
    metadata = json.loads(metadata_json)
    for field, operator in (("minimum_age", "gte"), ("maximum_age", "lte")):
        raw = metadata.get(field)
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s+(Years?|Months?)\s*", str(raw), flags=re.I)
        if match:
            value, unit = convert_measurement("age", float(match[1]), match[2])
            parsed["rules"].append({"id": f"metadata_{field}", "kind": "condition", "field": "age", "operator": operator,
                                    "value": value, "unit": unit, "type": "inclusion", "validated": True,
                                    "validation_basis": "structured_registry_field", "source_text": raw,
                                    "source_field": field, "source_start": None, "source_end": None, "study_id": study_id})
        elif raw and str(raw).upper() not in {"N/A", "NA", "NONE"}:
            parsed["unresolved"].append({"source_text": str(raw), "source_field": field, "reason": "Unsupported registry age unit", "status": "NEEDS_REVIEW"})
    if metadata.get("sex") in {"MALE", "FEMALE"}:
        parsed["rules"].append({"id": "metadata_sex", "kind": "condition", "field": "sex", "operator": "equals",
                                "value": metadata["sex"], "unit": None, "type": "inclusion", "validated": True,
                                "validation_basis": "structured_registry_field", "source_text": metadata["sex"],
                                "source_field": "sex", "source_start": None, "source_end": None, "study_id": study_id})
    # Hash all rule semantics and exact text; parser changes cannot reuse old approvals.
    parsed["contradictions"] = detect_contradictions(parsed["rules"])
    parsed["requires_human_validation"] = bool(parsed["unresolved"] or parsed["contradictions"] or not parsed["rules"])
    stable = {"text": text, "rules": parsed["rules"], "unresolved": parsed["unresolved"]}
    parsed["extraction_hash"] = hashlib.sha256(json.dumps(stable, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    parsed["stats"]["supported_rules_with_metadata"] = len(parsed["rules"])
    return parsed


def extract_study(study_id):
    study = require_study(study_id)
    metadata = {k: study.get(k) for k in ("minimum_age", "maximum_age", "sex")}
    result = copy.deepcopy(_extract_cached(study.get("eligibility_text") or "", study_id, json.dumps(metadata, sort_keys=True)))
    result.update(study_id=study_id, source_url=study["source_url"], notice=NOTICE)
    result["reviews"] = get_reviews(study_id, result["extraction_hash"])
    result["real_world_review_required"] = True
    return result


def evaluate_study(study_id, profile):
    parsed = extract_study(study_id)
    approved = {x["rule_id"] for x in parsed["reviews"] if x["decision"] == "approved"}
    rejected = {x["rule_id"] for x in parsed["reviews"] if x["decision"] == "rejected"}
    rules = [x for x in parsed["rules"] if x["id"] in approved]
    unresolved = parsed["unresolved"] + [
        {"rule_id": x["id"], "source_text": x["source_text"], "reason": "Reviewer rejected extraction" if x["id"] in rejected else "Supported rule awaits synthetic-demo review", "status": "NEEDS_REVIEW"}
        for x in parsed["rules"] if x["id"] not in approved]
    result = evaluate_profile(profile, rules, unresolved)
    source_conflicts = detect_contradictions([r for r in parsed["rules"] if r["id"] not in rejected])
    if source_conflicts:
        result.update(status="INSUFFICIENT_INFORMATION", contradictions=source_conflicts,
                      explanation="Conflicting supported source constraints remain approved or unreviewed. Resolve the extraction conflict before drawing a profile conclusion.")
    result.update(study_id=study_id, source_url=parsed["source_url"], extraction_hash=parsed["extraction_hash"], notice=NOTICE,
                  review_scope="Local synthetic demonstration, not expert or clinical validation")
    return result


def _leaves(rules):
    for rule in rules:
        if rule.get("children"):
            yield from _leaves(rule["children"])
        else:
            yield rule


def compare_studies(study_ids):
    studies = [require_study(x) for x in study_ids]
    extractions = [extract_study(x) for x in study_ids]
    fields = sorted({x.get("field") for extraction in extractions for x in _leaves(extraction["rules"]) if x.get("field")})
    rows = [{"field": field, "left": [r for r in _leaves(extractions[0]["rules"]) if r.get("field") == field],
             "right": [r for r in _leaves(extractions[1]["rules"]) if r.get("field") == field]} for field in fields]
    shared = sorted(set(studies[0].get("conditions", [])) & set(studies[1].get("conditions", [])))
    return {"studies": studies, "extractions": extractions, "comparison": rows, "shared_conditions": shared,
            "interpretation": "Descriptive comparison of these protocols. Recruitment countries do not set eligibility thresholds or establish causal regional differences.", "notice": NOTICE}


def dashboard():
    studies = get_studies()
    parsed = [extract_study(x["study_id"]) for x in studies]
    return {"study_count": len(studies), "regions": dict(Counter(c for x in studies for c in x.get("countries", []))),
            "overlapping_india_us": sum("India" in x.get("countries", []) and "United States" in x.get("countries", []) for x in studies),
            "conditions": dict(Counter(c for x in studies for c in x.get("conditions", []))),
            "statuses": dict(Counter(x.get("status") or "UNKNOWN" for x in studies)),
            "supported_rule_count": sum(len(x["rules"]) for x in parsed),
            "unresolved_criterion_count": sum(len(x["unresolved"]) for x in parsed),
            "reviewed_rule_count": sum(sum(r["decision"] == "approved" for r in x["reviews"]) for x in parsed),
            "notice": NOTICE}
