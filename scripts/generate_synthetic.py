"""Reuse the audited starter generator without making geographic clinical claims."""
import csv
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    path = ROOT / "legacy/TrialOps_Adaptive_Demo/trialops_adaptive_demo.py"
    spec = importlib.util.spec_from_file_location("audited_starter", path)
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    profiles = [{"patient_id": p["patient_id"].replace("SYN-IN-", "SYN-DEMO-"), "is_synthetic": True,
                 "age": p["age_years"], "bmi": p["bmi_kg_m2"], "hba1c": p["hba1c_percent"],
                 "type_2_diabetes": p["reported_type2_diabetes"], "severe_kidney_disease": p["reported_severe_kidney_disease"]}
                for p in legacy.generate_profiles(count=30, seed=2026)]
    output = ROOT / "data/synthetic"
    output.mkdir(parents=True, exist_ok=True)
    (output / "profiles.json").write_text(json.dumps(profiles, indent=2), encoding="utf-8")
    with (output / "profiles.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(profiles[0]))
        writer.writeheader()
        writer.writerows(profiles)
    (output / "provenance.json").write_text(json.dumps({"source": "Audited supplied synthetic demo generator", "seed": 2026,
            "count": len(profiles), "real_patient_data": False, "changes": "Canonical field aliases; removed geographic cohort label. No medical thresholds added."}, indent=2), encoding="utf-8")
    print(f"Wrote {len(profiles)} fabricated profiles, with explicit synthetic provenance.")


if __name__ == "__main__":
    main()
