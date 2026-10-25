"""Run with python -m scripts.ingest --per-region 30."""
import argparse
import json
from pathlib import Path

from backend.app.ingestion import ingest


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch real ClinicalTrials.gov v2 studies with provenance")
    parser.add_argument("--per-region", type=int, default=30)
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()
    result = ingest(args.per_region, page_size=args.page_size, root=args.data_dir)
    print(json.dumps({key: result[key] for key in ("run_id", "study_count", "country_study_counts", "india_us_overlap", "registry_counts", "missing_eligibility_count")}, indent=2))


if __name__ == "__main__":
    main()
