"""Build and verify a real hybrid index from the ingested ClinicalTrials.gov records."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.retrieval import RetrievalIndex


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--studies", type=Path, default=ROOT / "data/processed/studies.json")
    args = parser.parse_args()
    studies = json.loads(args.studies.read_text(encoding="utf-8"))
    by_id = {s["study_id"]: s for s in studies}
    started = time.perf_counter()
    index = RetrievalIndex(studies, allow_fallback=False)
    build_status = index.build()
    build_seconds = time.perf_counter() - started
    if build_status["semantic"] != "ready":
        raise RuntimeError(build_status["semantic_error"])
    results = []
    for mode in ("bm25", "semantic", "hybrid"):
        for query, country, status in [("HbA1c glycated hemoglobin inclusion criteria", None, None),
                                       ("diabetes treatment", "India", "RECRUITING"),
                                       ("body mass index BMI", "United States", None)]:
            hits = index.search(query, mode=mode, country=country, status=status)
            for hit in hits:
                assert by_id[hit["study_id"]][hit["source_field"]][hit["start"]:hit["end"]] == hit["text"]
            results.append({"query": query, "country": country, "status": status,
                            "search": index.last_search.copy(), "hits": hits})
    report = {"run_at_utc": datetime.now(timezone.utc).isoformat(), "study_count": len(studies),
              "index": build_status, "build_seconds": round(build_seconds, 3),
              "source_substring_verification": "passed for every returned chunk", "queries": results}
    report_path = ROOT / "reports/retrieval_smoke.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"report": str(report_path), "studies": len(studies), "index": build_status,
                      "build_seconds": report["build_seconds"]}, indent=2))


if __name__ == "__main__":
    main()
