"""Actual HTTP end-to-end run; no generated metrics or patient records."""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    calls = []
    examples = {}
    session = requests.Session()

    def call(method, path, payload=None):
        started = time.perf_counter()
        response = session.request(method, args.api + path, json=payload, timeout=(5, 180))
        response.raise_for_status()
        calls.append({"method": method, "path": path, "status_code": response.status_code,
                      "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                      "response_sha256": hashlib.sha256(response.content).hexdigest()})
        return response

    health = call("GET", "/health").json()
    studies = call("GET", "/studies").json()["studies"]
    assert len(studies) == health["study_count"] > 0
    india = next(s for s in studies if "India" in s["countries"])
    usa = next(s for s in studies if "United States" in s["countries"] and s["study_id"] != india["study_id"])
    examples["india_study"] = india["study_id"]
    examples["us_study"] = usa["study_id"]
    call("GET", "/dashboard")
    extracted = call("POST", "/extract", {"study_id": india["study_id"], "transformer": True}).json()
    assert extracted["transformer"]["status"] == "ok"
    assert not extracted["transformer"].get("truncated")
    examples["extraction"] = extracted
    compared = call("POST", "/compare", {"study_ids": [india["study_id"], usa["study_id"]]}).json()
    assert len(compared["studies"]) == 2
    evaluated = call("POST", "/evaluate", {"study_id": india["study_id"], "profile": {"patient_id": "SYN-E2E-001", "is_synthetic": True, "age": 35, "bmi": 26, "hba1c": 8, "type_2_diabetes": True}}).json()
    assert evaluated["status"] in {"INSUFFICIENT_INFORMATION", "MATCHES_KNOWN_CRITERIA", "DOES_NOT_MATCH_KNOWN_CRITERIA"}
    assert evaluated["real_world_review_required"] is True
    examples["synthetic_evaluation"] = evaluated
    asked = call("POST", "/ask", {"question": "Which diabetes studies mention BMI restrictions?", "mode": "hybrid"}).json()
    assert asked["evidence"]
    lookup = {s["study_id"]: s for s in studies}
    for evidence in asked["evidence"]:
        assert lookup[evidence["study_id"]][evidence["source_field"]][evidence["start"]:evidence["end"]] == evidence["text"]
    assert all(e["actual_mode"] == "hybrid" for e in asked["evidence"])
    examples["assistant"] = asked
    drafted = call("POST", "/ask", {"question": "Which diabetes studies mention BMI restrictions?", "mode": "hybrid", "generate": True}).json()
    assert drafted["generation"]["status"] == "generated_draft"
    assert drafted["generation"]["verified"] is False
    assert drafted["generation"]["text"]
    for context in drafted["generation"].get("source_context", []):
        assert lookup[context["study_id"]][context["source_field"]][context["start"]:context["end"]] == context["text"]
    examples["experimental_generated_draft"] = drafted
    for format in ("json", "csv", "html"):
        response = call("GET", f"/reports/{india['study_id']}?format={format}")
        assert "attachment" in response.headers["content-disposition"]
        (ROOT / "reports" / f"example_study_report.{format}").write_bytes(response.content)
    call("GET", "/metrics")
    ui = requests.get("http://127.0.0.1:8501/_stcore/health", timeout=10)
    assert ui.status_code == 200
    report = {"run_at_utc": datetime.now(timezone.utc).isoformat(), "status": "passed", "method": "Live HTTP requests against separate backend and frontend processes",
              "api_url": args.api, "ui_url": "http://127.0.0.1:8501", "study_count": len(studies), "calls": calls,
              "transformer_status": extracted["transformer"]["status"], "retrieval_modes": sorted({h["actual_mode"] for h in asked["evidence"]}),
              "source_offsets_verified": len(asked["evidence"]), "synthetic_profile_status": evaluated["status"],
              "local_generation_status": drafted["generation"]["status"], "generated_prose_verified": False,
              "review_note": "No source rules approved by this smoke script; test_api.py verifies approval mechanics with an isolated test database."}
    (ROOT / "reports" / "integration_smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (ROOT / "reports" / "integration_examples.json").write_text(json.dumps(examples, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
