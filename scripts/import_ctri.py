"""Compliant manual import; this command never contacts or scrapes CTRI."""
import argparse
import json
from pathlib import Path

from backend.app.ingestion import import_ctri


def main() -> None:
    parser = argparse.ArgumentParser(description="Import manually obtained public CTRI CSV/JSON records")
    parser.add_argument("path", type=Path)
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()
    result = import_ctri(args.path, root=args.data_dir)
    print(json.dumps({"study_count": result["study_count"], "registry_counts": result["registry_counts"]}, indent=2))


if __name__ == "__main__":
    main()
