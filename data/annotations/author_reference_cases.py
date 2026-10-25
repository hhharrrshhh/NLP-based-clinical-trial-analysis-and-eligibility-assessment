"""Authoring record for synthetic developer references; never imports the parser.

Run only when deliberately revising the reference set, not during evaluation.
Every expected semantic value below was specified from its source sentence.
These are engineering references, not expert annotations or clinical gold.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES: list[dict] = []


def leaf(field, operator, value=None, unit=None, *, lower=None, upper=None,
         negated=False, exclusion=False, unit_assumed=False):
    result = {"kind": "condition", "field": field, "operator": operator,
              "unit": unit, "negated": negated,
              "type": "exclusion_constraint" if exclusion or negated else "inclusion"}
    if lower is not None:
        result.update(lower=lower, upper=upper,
                      lower_inclusive=operator == "between_inclusive",
                      upper_inclusive=operator == "between_inclusive")
    else:
        result["value"] = value
    if unit is not None:
        result["unit_assumed"] = unit_assumed
    return result


def group(logic, *children, exclusion=False):
    return {"kind": "group", "logic": logic, "children": list(children),
            "type": "exclusion_constraint" if exclusion else "inclusion"}


def add(family, text, *rules, note="Complete unambiguous supported-field semantics."):
    # Families, rather than individual paraphrases, define synthetic source IDs.
    CASES.append({"case_id": f"DEVREF-{len(CASES) + 1:03d}", "family": family,
                  "study_id": "SYNTHETIC-REFERENCE-" + family, "split": "unassigned",
                  "text": text, "expected_executable": bool(rules),
                  "expected_rules": list(rules), "rationale": note,
                  "source": "developer-authored synthetic sentence",
                  "label_origin": "developer_reference", "reviewer": "not_expert_reviewed"})


def main():
    add("age-comparisons", "Age > 21 years", leaf("age", "gt", 21, "years"))
    add("age-comparisons", "Age at most 72 years", leaf("age", "lte", 72, "years"))
    add("age-comparisons", "Age no less than 24 years", leaf("age", "gte", 24, "years"))
    add("age-comparisons", "Age equals 45 years", leaf("age", "equals", 45, "years"))
    add("unicode-comparisons", "Age ≥ 22 years", leaf("age", "gte", 22, "years"))
    add("unicode-comparisons", "ＢＭＩ ≤ ２９ kg/m²", leaf("bmi", "lte", 29, "kg/m2"))
    add("bmi-comparisons", "Body mass index less than 32.5 kg/m2", leaf("bmi", "lt", 32.5, "kg/m2"))
    add("bmi-comparisons", "BMI more than 19 kg/m^2", leaf("bmi", "gt", 19, "kg/m2"))
    add("hba1c-comparisons", "HbA1c greater than or equal to 7.1 %", leaf("hba1c", "gte", 7.1, "%"))
    add("hba1c-comparisons", "Glycated hemoglobin below 9 percent", leaf("hba1c", "lt", 9, "%"))
    add("pressure-comparisons", "Systolic blood pressure <= 135 mmHg", leaf("systolic_bp", "lte", 135, "mmHg"))
    add("pressure-comparisons", "DBP over 75 mm Hg", leaf("diastolic_bp", "gt", 75, "mmHg"))
    add("unit-conversions", "Age >= 240 months", leaf("age", "gte", 20, "years"))
    add("unit-conversions", "HbA1c <= 48 mmol/mol", leaf("hba1c", "lte", 6.54304, "%"))
    add("unit-conversions", "SBP >= 16 kPa", leaf("systolic_bp", "gte", 120.009852134, "mmHg"))
    add("assumed-units", "Age >= 23", leaf("age", "gte", 23, "years", unit_assumed=True))
    add("assumed-units", "BMI <= 31", leaf("bmi", "lte", 31, "kg/m2", unit_assumed=True))
    add("inclusive-ranges", "Age from 21 to 70 years", leaf("age", "between_inclusive", unit="years", lower=21, upper=70))
    add("inclusive-ranges", "BMI 19–29 kg/m²", leaf("bmi", "between_inclusive", unit="kg/m2", lower=19, upper=29))
    add("exclusive-ranges", "Age between 21 and 70 years exclusive", leaf("age", "between_exclusive", unit="years", lower=21, upper=70))
    add("exclusive-ranges", "HbA1c between 6.2 and 8.4 % exclusive", leaf("hba1c", "between_exclusive", unit="%", lower=6.2, upper=8.4))
    add("chained-bounds", "21 <= age < 70 years", group("AND", leaf("age", "gte", 21, "years"), leaf("age", "lt", 70, "years")))
    add("chained-bounds", "HbA1c >= 6.2 % and < 8.4 %", group("AND", leaf("hba1c", "gte", 6.2, "%"), leaf("hba1c", "lt", 8.4, "%")))
    add("positive-diagnoses", "Diagnosed with T2DM", leaf("type_2_diabetes", "equals", True))
    add("positive-diagnoses", "Type 1 diabetes mellitus", leaf("type_1_diabetes", "equals", True))
    add("positive-diagnoses", "With hypertension", leaf("hypertension", "equals", True))
    add("positive-diagnoses", "Severe kidney disease", leaf("severe_kidney_disease", "equals", True))
    add("explicit-negation", "Without hypertension", leaf("hypertension", "equals", False, negated=True))
    add("explicit-negation", "Must not have severe renal impairment", leaf("severe_renal_impairment", "equals", False, negated=True))
    add("explicit-negation", "Not be pregnant", leaf("pregnant", "equals", False, negated=True))
    add("explicit-negation", "Negative for T1DM", leaf("type_1_diabetes", "equals", False, negated=True))
    add("older-younger", "Age 24 years or older", leaf("age", "gte", 24, "years"))
    add("older-younger", "Age 68 years or younger", leaf("age", "lte", 68, "years"))
    add("explicit-and", "Age >= 21 years and BMI < 29 kg/m2", group("AND", leaf("age", "gte", 21, "years"), leaf("bmi", "lt", 29, "kg/m2")))
    add("explicit-or", "HbA1c < 7.5 % or BMI < 28 kg/m2", group("OR", leaf("hba1c", "lt", 7.5, "%"), leaf("bmi", "lt", 28, "kg/m2")))
    add("parenthesized-logic", "Age >= 21 years and (BMI < 29 kg/m2 or HbA1c < 7.5 %)", group("AND", leaf("age", "gte", 21, "years"), group("OR", leaf("bmi", "lt", 29, "kg/m2"), leaf("hba1c", "lt", 7.5, "%"))))
    add("scoped-negation", "No T2DM and not be pregnant", group("AND", leaf("type_2_diabetes", "equals", False, negated=True), leaf("pregnant", "equals", False, negated=True)))
    add("exclusion-positive", "Exclusion Criteria:\n- Pregnancy", group("NOT", leaf("pregnant", "equals", True, exclusion=True), exclusion=True))
    add("exclusion-or", "Exclusion Criteria:\n- T1DM or severe renal impairment", group("NOT", group("OR", leaf("type_1_diabetes", "equals", True, exclusion=True), leaf("severe_renal_impairment", "equals", True, exclusion=True), exclusion=True), exclusion=True))
    add("exclusion-negative", "Exclusion Criteria:\n- Without hypertension", group("NOT", leaf("hypertension", "equals", False, negated=True, exclusion=True), exclusion=True))
    add("distinct-bullets", "Inclusion Criteria:\n- Age >= 21 years\n- BMI <= 29 kg/m2", leaf("age", "gte", 21, "years"), leaf("bmi", "lte", 29, "kg/m2"))
    add("exact-prose", "Participants must be between 21 and 70 years of age and must not have severe renal impairment.", group("AND", leaf("age", "between_inclusive", unit="years", lower=21, upper=70), leaf("severe_renal_impairment", "equals", False, negated=True)))
    # Unambiguous, representable paraphrases are deliberately labeled by meaning,
    # even when this grammar may miss them. Do not lower expectations to outputs.
    add("semantic-paraphrases", "Age must exceed 21 years", leaf("age", "gt", 21, "years"), note="Unambiguous greater-than meaning; lexical grammar coverage is being tested.")
    add("semantic-paraphrases", "BMI is lower than 29 kg/m2", leaf("bmi", "lt", 29, "kg/m2"), note="Unambiguous less-than meaning; lexical grammar coverage is being tested.")
    add("semantic-paraphrases", "No pregnancy", leaf("pregnant", "equals", False, negated=True))
    unsupported = [
        ("temporal", "Age >= 21 years at screening", "Age must be anchored to a visit."),
        ("temporal", "HbA1c < 8 % within the past 3 months", "Temporal measurement validity is unsupported."),
        ("duration", "T2DM for at least 12 months", "Disease-duration reasoning is unsupported."),
        ("duration", "History of hypertension", "Historical and current diagnosis differ."),
        ("discretion", "Age >= 21 years unless the investigator approves", "An exception changes execution scope."),
        ("discretion", "Adequate renal function", "No measurable threshold is supplied."),
        ("partial-clause", "Age >= 21 years and willing to attend visits", "A complete criterion contains an unsupported conjunct."),
        ("partial-clause", "BMI < 29 kg/m2. Except pregnant participants.", "A sentence boundary does not remove an exception."),
        ("mixed-logic", "Age >= 21 years and BMI < 29 kg/m2 or hypertension", "Unparenthesized mixed logic is ambiguous."),
        ("mixed-logic", "No T2DM or hypertension", "Negation scope is ambiguous."),
        ("mixed-logic", "BMI < 29 kg/m2 and/or T2DM", "And/or is not an executable Boolean tree."),
        ("missing-units", "HbA1c >= 48", "Dual common scales make a bare threshold ambiguous."),
        ("missing-units", "SBP < 130", "Pressure source unit is missing."),
        ("incompatible-units", "Age > 21 kg/m2", "The age unit is dimensionally incompatible."),
        ("incompatible-units", "BMI < 29 mg/dL", "BMI cannot use concentration units."),
        ("incompatible-units", "HbA1c < 8 mmol/L", "Concentration and HbA1c ratio units differ."),
        ("unsupported-fields", "eGFR > 60 mL/min/1.73m2", "eGFR is outside the field model."),
        ("unsupported-fields", "Fasting glucose >= 126 mg/dL", "Glucose is outside the field model."),
        ("unsupported-fields", "Females only", "Sex constraints are outside this grammar."),
        ("nonspecific-diagnoses", "Diabetes", "Diabetes subtype cannot be inferred."),
        ("nonspecific-diagnoses", "Renal impairment", "Severity must not be invented."),
        ("medications", "Taking metformin 1000 mg daily", "Medication and dose reasoning is unsupported."),
        ("medications", "Stable insulin dose for 8 weeks", "Stability and dose history are unsupported."),
        ("conditional-list", "Inclusion Criteria:\nAny of the following:\n- Age >= 21 years\n- BMI < 29 kg/m2", "The unresolved introduction scopes the list."),
        ("wrapped-exception", "Inclusion Criteria:\n- Age >= 21 years\n  with investigator approval", "Wrapped qualification is part of the criterion."),
        ("nested-exception", "Inclusion Criteria:\n- BMI < 29 kg/m2\n  - unless pregnant", "A nested exception changes the parent rule."),
        ("ambiguous-quantity", "Approximately age 21 years", "An approximate threshold is not exact."),
        ("missing-threshold", "BMI in normal range", "No supported numeric threshold is supplied."),
        ("empty-source", "", "There is no criterion to execute."),
        ("heading-only", "Exclusion Criteria:", "A heading alone supplies no executable constraint."),
    ]
    for family, text, note in unsupported:
        add(family, text, note=note)
    # Stratify by the authored disposition, never by a prediction. Sorting whole
    # families by stable SHA256 avoids paraphrase leakage and gives every split
    # examples of both dispositions despite this small number of families.
    family_split = {}
    for positive in (True, False):
        families = {case["family"] for case in CASES if case["expected_executable"] is positive}
        ordered = sorted(families, key=lambda family: hashlib.sha256(("developer-reference-v1:" + family).encode()).hexdigest())
        for rank, family in enumerate(ordered):
            family_split[family] = "train" if rank < int(.6 * len(ordered)) else "dev" if rank < int(.8 * len(ordered)) else "test"
    for case in CASES:
        case["split"] = family_split[case["family"]]
    payload = {"schema_version": "developer-reference-v1", "label_origin": "developer_reference",
               "expert_reviewed": False, "blinded": False,
               "authoring": "Expected semantics are explicitly authored above, without parser imports or predictions. The parser existed before these references; the author read its documented contract. These references are not independent clinical ground truth.",
               "positive_definition": "Complete, unambiguous constraints expressible in the declared field/operator/unit/Boolean model, including explicit lexical generalization challenges.",
               "split_definition": "Separately for authored executable/unsupported dispositions, sort whole families by SHA256(developer-reference-v1:family); first floor(0.6*K) families train, next through floor(0.8*K) dev, remainder test. Assign all family cases together. Splits use labels, never predictions. No model is trained on this set. Test is a developer reference holdout, not blinded external validation.",
               "cases": CASES}
    (HERE / "developer_reference_cases.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # A practical case-level CSV accompanies structured JSON. Rule rows preserve
    # the complete source span; their JSON signature supplies exact atom meaning.
    fields = ["annotation_id", "case_id", "study_id", "split", "source", "label_origin", "reviewer", "text", "span_start", "span_end", "exact_span", "entity", "category", "operator", "value", "unit", "negation", "type", "logical_signature", "executable", "rationale"]
    def atom_rows(rule):
        if rule["kind"] == "group":
            return [atom for child in rule["children"] for atom in atom_rows(child)]
        return [rule]
    with (HERE / "developer_reference_annotations.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for case in CASES:
            atoms = [atom for rule in case["expected_rules"] for atom in atom_rows(rule)] or [{}]
            for index, atom in enumerate(atoms, 1):
                field = atom.get("field", "")
                category = "measurement" if atom.get("unit") else "condition" if field else "unsupported_criterion"
                writer.writerow({"annotation_id": f'{case["case_id"]}-{index}', "case_id": case["case_id"],
                                 **{key: case[key] for key in ("study_id", "split", "source", "label_origin", "reviewer", "text", "rationale")},
                                 "span_start": 0, "span_end": len(case["text"]), "exact_span": case["text"],
                                 "entity": field, "category": category, "operator": atom.get("operator", ""),
                                 "value": json.dumps({key: atom[key] for key in ("value", "lower", "upper", "lower_inclusive", "upper_inclusive") if key in atom}),
                                 "unit": atom.get("unit"), "negation": atom.get("negated"), "type": atom.get("type", "unsupported"),
                                 "logical_signature": json.dumps(case["expected_rules"], sort_keys=True),
                                 "executable": case["expected_executable"]})


if __name__ == "__main__":
    main()
