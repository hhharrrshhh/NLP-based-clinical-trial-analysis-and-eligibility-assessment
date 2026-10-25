"""Actual CPU generation on a real retrieved study, with input/output provenance."""
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
import psutil
from backend.app.generation import LocalGenerator
from backend.app.store import get_studies
from backend.app.retrieval import RetrievalIndex

ROOT = Path(__file__).resolve().parents[1]


def main():
    studies = get_studies()
    index = RetrievalIndex(studies, semantic=False)
    hits = index.search("HbA1c glycated hemoglobin inclusion criteria", k=3, mode="bm25")
    if not hits:
        raise RuntimeError("No real evidence available")
    generator = LocalGenerator()
    result = generator.generate("What HbA1c requirement is explicitly written in this source excerpt?", hits)
    report = {"run_at_utc": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
              "rss_after_mib": round(psutil.Process().memory_info().rss / 2**20, 3), "result": result,
              "status": "passed" if result["status"] == "generated_draft" and result.get("text") else "failed",
              "scope": "Inference execution only; no claim of answer correctness or clinical validation."}
    (ROOT / "reports/generation_smoke.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
