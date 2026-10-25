"""Prepare source documents for independent annotation; create no semantic labels."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    columns = json.loads((HERE / "annotation_schema.json").read_text(encoding="utf-8"))["required"]
    studies = json.loads((ROOT / "data/processed/studies.json").read_text(encoding="utf-8"))
    with (HERE / "registry_annotation_queue.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for study in studies:
            study_id = study["study_id"]
            source = study["eligibility_text"]
            row = dict.fromkeys(columns, "")
            row.update(annotation_id=f"UNANNOTATED-{study_id}-document", case_id=f"{study_id}-document",
                       study_id=study_id, split="train" if int(hashlib.sha256(study_id.encode()).hexdigest(), 16) % 10 < 8 else "test",
                       source=study["source_url"], label_origin="unannotated", reviewer="unassigned",
                       text=source, span_start=0, span_end=len(source), exact_span=source,
                       rationale="Full source document queued for independent criterion annotation; all semantic labels are missing.")
            writer.writerow(row)


if __name__ == "__main__":
    main()
