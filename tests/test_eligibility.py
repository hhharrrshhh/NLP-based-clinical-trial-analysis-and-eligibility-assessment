"""Decision-boundary and three-valued logic checks on synthetic observations."""
import math

import pytest

from backend.app.eligibility import evaluate_profile
from backend.app.nlp import extract


def assess(text, **attributes):
    parsed = extract(text, "SYNTHETIC-GRAMMAR-TEST")
    return evaluate_profile({"is_synthetic": True, **attributes}, parsed["rules"], parsed["unresolved"])


@pytest.mark.parametrize("text,age,status", [
    ("Age >= 18 years", 18, "MATCHES_KNOWN_CRITERIA"),
    ("Age > 18 years", 18, "DOES_NOT_MATCH_KNOWN_CRITERIA"),
    ("Age <= 65 years", 65, "MATCHES_KNOWN_CRITERIA"),
    ("Age < 65 years", 65, "DOES_NOT_MATCH_KNOWN_CRITERIA"),
    ("Age 18-65 years", 18, "MATCHES_KNOWN_CRITERIA"),
    ("Age 18-65 years", 65, "MATCHES_KNOWN_CRITERIA"),
    ("Age between 18 and 65 years exclusive", 18, "DOES_NOT_MATCH_KNOWN_CRITERIA"),
    ("18 <= age < 65 years", 65, "DOES_NOT_MATCH_KNOWN_CRITERIA"),
])
def test_numeric_boundaries(text, age, status):
    assert assess(text, age=age)["status"] == status


@pytest.mark.parametrize("value", [None, "18", True, math.inf, -math.inf, math.nan, {}, {"value": 18, "unit": "mg/dL"}])
def test_missing_and_malformed_measurements_never_pass(value):
    result = assess("Age >= 18 years", age=value)
    assert result["status"] == "INSUFFICIENT_INFORMATION"
    assert result["rule_results"][0]["result"] == "UNKNOWN"


@pytest.mark.parametrize("profile", [{}, {"is_synthetic": False}, {"is_synthetic": "true"}, {"is_synthetic": 1}])
def test_real_or_unmarked_profiles_are_rejected(profile):
    with pytest.raises(ValueError, match="Synthetic"):
        evaluate_profile(profile, [])


def test_empty_rules_are_insufficient_information():
    assert evaluate_profile({"is_synthetic": True}, [])["status"] == "INSUFFICIENT_INFORMATION"


def test_unvalidated_rule_is_not_executed():
    rule = {"kind": "condition", "field": "age", "operator": "gte", "value": 18, "unit": "years"}
    result = evaluate_profile({"age": 25, "is_synthetic": True}, [rule])
    assert result["status"] == "INSUFFICIENT_INFORMATION"
    assert result["rule_results"][0]["result"] == "UNKNOWN"


def test_exclusion_negation_and_missing_boolean():
    text = "Exclusion Criteria:\n- Severe renal impairment"
    assert assess(text, severe_renal_impairment=True)["status"] == "DOES_NOT_MATCH_KNOWN_CRITERIA"
    assert assess(text, severe_renal_impairment=False)["status"] == "MATCHES_KNOWN_CRITERIA"
    assert assess(text)["status"] == "INSUFFICIENT_INFORMATION"
    assert assess("No T2DM", type_2_diabetes=False)["status"] == "MATCHES_KNOWN_CRITERIA"


def test_empty_positive_diagnosis_list_never_implies_absence():
    assert assess("No T2DM", conditions=[])["status"] == "INSUFFICIENT_INFORMATION"
    assert assess("No T2DM", conditions={"type_2_diabetes": False})["status"] == "MATCHES_KNOWN_CRITERIA"
    assert assess("T2DM", conditions=["type_2_diabetes"])["status"] == "MATCHES_KNOWN_CRITERIA"


@pytest.mark.parametrize("logic,age,bmi,expected", [
    ("and", 25, 25, "MATCHES_KNOWN_CRITERIA"),
    ("and", 25, None, "INSUFFICIENT_INFORMATION"),
    ("and", 17, None, "DOES_NOT_MATCH_KNOWN_CRITERIA"),
    ("or", 25, None, "MATCHES_KNOWN_CRITERIA"),
    ("or", 17, None, "INSUFFICIENT_INFORMATION"),
    ("or", 17, 35, "DOES_NOT_MATCH_KNOWN_CRITERIA"),
    ("or", None, None, "INSUFFICIENT_INFORMATION"),
])
def test_three_valued_logic(logic, age, bmi, expected):
    assert assess(f"Age >= 18 years {logic} BMI < 30 kg/m2", age=age, bmi=bmi)["status"] == expected


def test_not_of_or_obeys_exclusion_scope():
    text = "Exclusion Criteria:\n- Age < 18 years or BMI >= 30 kg/m2"
    assert assess(text, age=25, bmi=29)["status"] == "MATCHES_KNOWN_CRITERIA"
    assert assess(text, age=17, bmi=None)["status"] == "DOES_NOT_MATCH_KNOWN_CRITERIA"
    assert assess(text, age=25, bmi=None)["status"] == "INSUFFICIENT_INFORMATION"


def test_unknown_criteria_retained_even_when_known_rule_fails():
    text = "Inclusion Criteria:\n- Age >= 18 years\n- Willing to attend all visits"
    result = assess(text, age=17)
    assert result["status"] == "DOES_NOT_MATCH_KNOWN_CRITERIA"
    assert result["unresolved"]
    assert assess(text, age=25)["status"] == "INSUFFICIENT_INFORMATION"


@pytest.mark.parametrize("text", [
    "Age > 65 years\n\nAge <= 65 years",
    "Age 65-18 years",
    "T2DM\n\nNo T2DM",
    "Inclusion Criteria:\n- Age >= 18 years\nExclusion Criteria:\n- Age >= 18 years",
])
def test_contradictions_force_review_instead_of_patient_failure(text):
    result = assess(text, age=30, type_2_diabetes=True)
    assert result["status"] == "INSUFFICIENT_INFORMATION"
    assert result["contradictions"]


def test_or_branches_do_not_generate_false_contradictions():
    result = assess("Age < 18 years or Age > 65 years", age=16)
    assert result["status"] == "MATCHES_KNOWN_CRITERIA"
    assert not result["contradictions"]


def test_units_are_converted_without_threshold_switches():
    assert assess("Age >= 18 years", age={"value": 216, "unit": "months"})["status"] == "MATCHES_KNOWN_CRITERIA"
    result = assess("SBP >= 16 kPa", systolic_bp={"value": 16, "unit": "kPa"})
    assert result["status"] == "MATCHES_KNOWN_CRITERIA"
    assert result["rule_results"][0]["normalized_patient_value"] == pytest.approx(120.009852)
    assert assess("HbA1c <= 53 mmol/mol", hba1c={"value": 53, "unit": "mmol/mol"})["status"] == "MATCHES_KNOWN_CRITERIA"
    assert assess("DBP < 90 mmHg", diastolic_bp=90)["status"] == "DOES_NOT_MATCH_KNOWN_CRITERIA"


def test_legacy_profile_numeric_aliases_remain_usable():
    result = assess("Age >= 18 years and T2DM", age_years=20, reported_type2_diabetes=True)
    assert result["status"] == "MATCHES_KNOWN_CRITERIA"


def test_every_rule_result_includes_source_and_explanation():
    result = assess("Age >= 18 years", age=20)
    rule_result = result["rule_results"][0]
    assert rule_result["evidence"]["source_text"] == "Age >= 18 years"
    assert rule_result["evidence"]["study_id"] == "SYNTHETIC-GRAMMAR-TEST"
    assert rule_result["patient_value"] == 20
    assert rule_result["normalized_condition"] == {"field": "age", "operator": "gte", "value": 18, "unit": "years"}
    assert rule_result["explanation"]
    assert result["real_world_review_required"]
