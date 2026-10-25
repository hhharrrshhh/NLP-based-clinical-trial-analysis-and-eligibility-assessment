#!/usr/bin/env python3
"""TrialOps Adaptive AI: illustrative clinical-trial eligibility simulator.

IMPORTANT: All patient profiles and trial protocols in this demonstration are
SYNTHETIC/FICTIONAL. Thresholds are NOT ICMR, FDA, trial registry or clinical
practice standards. This is NOT clinical decision support and does not diagnose
conditions or establish real clinical-trial eligibility.

Python standard library only; run: python trialops_adaptive_demo.py
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent


def generate_profiles(count: int = 30, seed: int = 2026) -> list[dict[str, Any]]:
    if count < 5:
        raise ValueError("count must be at least 5 so boundary cases are included")
    rng = random.Random(seed)
    # Intentional boundary, exclusion and missing-value cases make the demo testable.
    samples = [
        (35, 26.0, 8.0, True, False),  # potentially passes both hypothetical protocols
        (19, 23.0, 7.5, True, False),  # differs because of trial-specific age range
        (44, 36.0, 8.0, True, False),  # differs because of trial-specific BMI range
        (50, 27.0, None, True, False), # cannot conclude: HbA1c unknown
        (52, 29.0, 9.0, True, True),   # exclusion condition
    ]
    while len(samples) < count:
        age = rng.randint(18, 74)
        bmi = round(rng.uniform(18, 41), 1)
        hba1c = round(rng.uniform(5.5, 12.0), 1)
        has_t2d = rng.random() < 0.83
        has_severe_kidney_disease = rng.random() < 0.12
        if rng.random() < 0.10:
            hba1c = None
        if rng.random() < 0.04:
            has_severe_kidney_disease = None
        samples.append((age, bmi, hba1c, has_t2d, has_severe_kidney_disease))
    result = []
    for ix, (age, bmi, hba1c, has_t2d, kidney) in enumerate(samples, 1):
        result.append({
            "patient_id": f"SYN-IN-{ix:03d}",
            "cohort_label": "synthetic_India_demo",
            "age_years": age,
            "bmi_kg_m2": bmi,
            "hba1c_percent": hba1c,
            "reported_type2_diabetes": has_t2d,
            "reported_severe_kidney_disease": kidney,
            "is_synthetic": True,
        })
    return result


def range_check(label: str, value: Any, low: float, high: float, unit: str) -> tuple[str, str]:
    if value is None:
        return "unknown", f"{label}: missing ({unit})"
    if not (low <= value <= high):
        return "fail", f"{label}: {value} {unit} outside this DEMO trial's [{low}, {high}]"
    return "pass", f"{label}: {value} {unit} within this DEMO trial's range"


def boolean_check(label: str, value: Any, expected: bool) -> tuple[str, str]:
    if value is None:
        return "unknown", f"{label}: missing"
    if value is not expected:
        return "fail", f"{label}: {value}; DEMO trial requires {expected}"
    return "pass", f"{label}: matches DEMO requirement"


def assess(profile: dict[str, Any], trial: dict[str, Any]) -> dict[str, str]:
    checks: list[tuple[str, str]] = []
    for feature, unit in [("age_years", "years"), ("bmi_kg_m2", "kg/m2"), ("hba1c_percent", "%")]:
        bounds = trial["constraints"][feature]
        checks.append(range_check(feature, profile[feature], bounds["min"], bounds["max"], unit))
    for feature in ("reported_type2_diabetes", "reported_severe_kidney_disease"):
        checks.append(boolean_check(feature, profile[feature], trial["constraints"][feature]))

    failed = [explanation for state, explanation in checks if state == "fail"]
    unknown = [explanation for state, explanation in checks if state == "unknown"]
    # Explicit failures override unknowns; missing data never produces 'passes_all_demo_rules'.
    if failed:
        status = "fails_demo_rules"
    elif unknown:
        status = "needs_review"
    else:
        status = "passes_all_demo_rules"
    return {
        "patient_id": profile["patient_id"],
        "trial_id": trial["trial_id"],
        "trial_country": trial["trial_country"],
        "status": status,
        "failed_constraints": " | ".join(failed),
        "missing_information": " | ".join(unknown),
        "explanation": " | ".join(e for _, e in checks),
        "is_synthetic": "True",
    }


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    if not records:
        raise ValueError("No data to write")
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)


def run(output_dir: Path, count: int = 30, seed: int = 2026) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    trials = json.loads((BASE / "fictional_trial_protocols.json").read_text(encoding="utf-8"))
    profiles = generate_profiles(count, seed)
    evaluations = [assess(p, trial) for p in profiles for trial in trials]
    write_csv(output_dir / "synthetic_india_profiles.csv", profiles)
    write_csv(output_dir / "fictional_trial_comparison.csv", evaluations)
    print("SYNTHETIC PROFILES — NOT REAL PATIENT DATA")
    print("FICTIONAL PROTOCOLS — NOT ICMR/FDA OR MEDICAL GUIDELINES")
    print(f"Wrote {len(profiles)} synthetic profiles and {len(evaluations)} rule evaluations to: {output_dir}")
    for trial in trials:
        counts = Counter(x["status"] for x in evaluations if x["trial_id"] == trial["trial_id"])
        print(f"{trial['trial_id']}: {dict(counts)}")
    print("Example comparison of profile SYN-IN-002:")
    for r in evaluations:
        if r["patient_id"] == "SYN-IN-002":
            print(f"  {r['trial_id']}: {r['status']} | {r['failed_constraints'] or 'no failed constraints'}")


def self_test() -> None:
    trials = json.loads((BASE / "fictional_trial_protocols.json").read_text(encoding="utf-8"))
    profiles = generate_profiles()
    assert len(profiles) == 30 and len({p['patient_id'] for p in profiles}) == 30
    assert all(p["is_synthetic"] for p in profiles)
    # Patient 002 is age 19, a deliberate trial-specific difference.
    p = profiles[1]
    assert assess(p, trials[0])["status"] == "passes_all_demo_rules"
    assert assess(p, trials[1])["status"] == "fails_demo_rules"
    # Missing HbA1c must not result in passing.
    p = profiles[3]
    assert assess(p, trials[0])["status"] == "needs_review"
    # Exclusion condition yields fail.
    p = profiles[4]
    assert assess(p, trials[0])["status"] == "fails_demo_rules"
    print("All four demo sanity checks passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic profiles and compare fictional trial-specific eligibility rules.")
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output-dir", type=Path, default=BASE)
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    if args.test:
        self_test()
    else:
        run(args.output_dir, args.count, args.seed)
