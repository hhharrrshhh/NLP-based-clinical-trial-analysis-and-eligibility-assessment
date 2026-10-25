"""Read the local normalized corpus; never silently substitute fictional trials."""
from __future__ import annotations

import json
from pathlib import Path

from .ingestion import data_dir


def get_studies() -> list[dict]:
    path = data_dir() / "processed" / "studies.json"
    if not path.exists():
        return []
    studies = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(studies, list):
        raise ValueError("Normalized studies must be a JSON array")
    return studies


def get_study(study_id: str) -> dict | None:
    return next((study for study in get_studies() if study["study_id"] == study_id), None)


def get_metadata() -> dict:
    path: Path = data_dir() / "processed" / "study_metadata.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"study_count": 0}
