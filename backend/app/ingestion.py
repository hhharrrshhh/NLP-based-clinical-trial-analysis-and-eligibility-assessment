"""ClinicalTrials.gov v2 ingestion with immutable raw pages and record provenance."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

API_URL = "https://clinicaltrials.gov/api/v2/studies"
REGIONS = ("India", "United States")
ROOT = Path(__file__).resolve().parents[2]
LOG = logging.getLogger(__name__)


class IngestionError(RuntimeError):
    """The source could not be safely retrieved or normalized."""


def data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", str(ROOT / "data"))).resolve()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _object(parent: dict, name: str) -> dict:
    value = parent.get(name)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise IngestionError(f"Schema changed: {name} must be an object")
    return value


def _list(parent: dict, name: str) -> list:
    value = parent.get(name)
    if value is None:
        return []
    if not isinstance(value, list):
        raise IngestionError(f"Schema changed: {name} must be an array")
    return value


def _text(parent: dict, name: str) -> str | None:
    value = parent.get(name)
    if value is not None and not isinstance(value, str):
        raise IngestionError(f"Schema changed: {name} must be a string or null")
    return value


def normalize_study(raw: dict, provenance: dict) -> dict:
    if not isinstance(raw, dict):
        raise IngestionError("Schema changed: study must be an object")
    protocol = _object(raw, "protocolSection")
    identity = _object(protocol, "identificationModule")
    study_id = identity.get("nctId", "")
    if not isinstance(study_id, str) or not re.fullmatch(r"NCT\d{8}", study_id):
        raise IngestionError("Missing or invalid NCT identifier; record not invented")
    eligibility = _object(protocol, "eligibilityModule")
    status = _object(protocol, "statusModule")
    description = _object(protocol, "descriptionModule")
    locations = []
    for location in _list(_object(protocol, "contactsLocationsModule"), "locations"):
        if not isinstance(location, dict):
            raise IngestionError("Schema changed: location must be an object")
        locations.append({key: location.get(key) for key in ("facility", "city", "state", "zip", "country", "status")})
    countries = sorted({loc["country"] for loc in locations if loc.get("country")})
    return {
        "study_id": study_id,
        "title": _text(identity, "briefTitle") or _text(identity, "officialTitle") or "",
        "conditions": _list(_object(protocol, "conditionsModule"), "conditions"),
        "countries": countries,
        "status": _text(status, "overallStatus"),
        "phase": _list(_object(protocol, "designModule"), "phases"),
        "eligibility_text": _text(eligibility, "eligibilityCriteria") or "",
        "minimum_age": _text(eligibility, "minimumAge"),
        "maximum_age": _text(eligibility, "maximumAge"),
        "sex": _text(eligibility, "sex"),
        "healthy_volunteers": eligibility.get("healthyVolunteers"),
        "description": "\n\n".join(str(description[key]) for key in ("briefSummary", "detailedDescription") if description.get(key)),
        "source_url": f"https://clinicaltrials.gov/study/{study_id}",
        "last_update": _object(status, "lastUpdatePostDateStruct").get("date"),
        "retrieved_at": provenance["retrieved_at"],
        "registry": "ClinicalTrials.gov",
        "locations": locations,
        "provenance": [provenance],
    }


def fetch_page(session: requests.Session, params: dict, *, retries: int = 3, sleep=time.sleep) -> requests.Response:
    """Retry only transient network/HTTP errors; never bypass access controls."""
    if retries < 0:
        raise ValueError("retries must be nonnegative")
    for attempt in range(retries + 1):
        try:
            response = session.get(API_URL, params=params, timeout=(10, 60), headers={"Accept": "application/json", "User-Agent": "TrialOps-Adaptive-AI/1.0 academic-research"})
            if response.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                retry_after = response.headers.get("Retry-After", "")
                sleep(min(float(retry_after), 60) if retry_after.isdigit() else min(2 ** attempt, 8))
                continue
            response.raise_for_status()
            return response
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt == retries:
                raise IngestionError(f"ClinicalTrials.gov unavailable after {attempt + 1} attempts: {exc}") from exc
            sleep(min(2 ** attempt, 8))
        except requests.HTTPError as exc:
            raise IngestionError(f"ClinicalTrials.gov HTTP {exc.response.status_code}; no records fabricated") from exc
    raise IngestionError("Retry limit exhausted")


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for key, value in row.items() if key in fields})


def save_dataset(studies: list[dict], root: Path, metadata: dict | None = None) -> dict:
    processed = root / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    studies = sorted(studies, key=lambda study: study["study_id"])
    counts = Counter(country for study in studies for country in study["countries"])
    result = dict(metadata or {})
    result.update({
        "schema_version": 1,
        "generated_at": utc_now(),
        "study_count": len(studies),
        "country_study_counts": dict(sorted(counts.items())),
        "india_us_overlap": sum(all(region in study["countries"] for region in REGIONS) for study in studies),
        "registry_counts": dict(Counter(study["registry"] for study in studies)),
        "missing_eligibility_count": sum(not study["eligibility_text"].strip() for study in studies),
        "record_provenance": {study["study_id"]: study["provenance"] for study in studies},
    })
    write_json(processed / "studies.json", studies)
    _write_csv(processed / "studies.csv", studies, ["study_id", "title", "conditions", "countries", "status", "phase", "minimum_age", "maximum_age", "sex", "description", "source_url", "last_update", "retrieved_at", "registry"])
    _write_csv(processed / "eligibility_criteria.csv", studies, ["study_id", "eligibility_text", "minimum_age", "maximum_age", "sex", "source_url", "retrieved_at"])
    locations = [{"study_id": study["study_id"], "source_url": study["source_url"], **location} for study in studies for location in study["locations"]]
    _write_csv(processed / "study_locations.csv", locations, ["study_id", "facility", "city", "state", "zip", "country", "status", "source_url"])
    write_json(processed / "study_metadata.json", result)
    return result


def ingest(per_region: int = 30, *, root: Path | None = None, page_size: int = 20, session: requests.Session | None = None) -> dict:
    if not 1 <= per_region <= 1000 or not 1 <= page_size <= 1000:
        raise ValueError("per_region and page_size must be between 1 and 1000")
    root = (root or data_dir()).resolve()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    raw_dir = root / "raw" / "clinicaltrials" / run_id
    raw_dir.mkdir(parents=True, exist_ok=False)
    source_session = session or requests.Session()
    records: dict[str, dict] = {}
    manifest: dict[str, Any] = {"run_id": run_id, "started_at": utc_now(), "source_api": API_URL, "source_documentation": "https://clinicaltrials.gov/data-api/api", "condition_query": "Type 2 Diabetes", "per_region_requested": per_region, "selection": "API relevance order, all recruitment statuses; convenience sample, not representative", "pages": [], "queries": {}, "skipped": [], "status": "running"}
    try:
        for region in REGIONS:
            params: dict[str, Any] = {"format": "json", "query.cond": "Type 2 Diabetes", "query.locn": region, "sort": "@relevance", "countTotal": "true", "pageSize": min(page_size, per_region)}
            region_ids: set[str] = set()
            seen_tokens: set[str] = set()
            page_number = 0
            while len(region_ids) < per_region:
                page_number += 1
                if page_number > 100:
                    raise IngestionError("Pagination limit exceeded")
                response = fetch_page(source_session, params)
                timestamp = utc_now()
                name = f"{region.lower().replace(' ', '_')}_{page_number:03d}.json"
                raw_path = raw_dir / name
                raw_path.write_bytes(response.content)
                provenance = {"retrieved_at": timestamp, "source_url": response.url, "source_api": API_URL, "query": dict(params), "query_region": region, "raw_file": raw_path.relative_to(root).as_posix(), "sha256": hashlib.sha256(response.content).hexdigest()}
                manifest["pages"].append(provenance)
                write_json(raw_path.with_suffix(".provenance.json"), provenance)
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise IngestionError("API returned invalid JSON; raw response retained") from exc
                if not isinstance(payload, dict) or not isinstance(payload.get("studies"), list):
                    raise IngestionError("Schema changed: expected studies array")
                if region not in manifest["queries"]:
                    manifest["queries"][region] = {"query": dict(params), "total_available_reported": payload.get("totalCount")}
                for raw in payload["studies"]:
                    study = normalize_study(raw, provenance)
                    if region not in study["countries"]:
                        manifest["skipped"].append({"study_id": study["study_id"], "query_region": region, "reason": "No matching country in listed locations"})
                        continue
                    if study["study_id"] in region_ids:
                        continue
                    region_ids.add(study["study_id"])
                    if study["study_id"] in records:
                        records[study["study_id"]]["provenance"].append(provenance)
                    else:
                        records[study["study_id"]] = study
                    if len(region_ids) >= per_region:
                        break
                token = payload.get("nextPageToken")
                if len(region_ids) >= per_region or not token:
                    break
                if not isinstance(token, str) or token in seen_tokens:
                    raise IngestionError("Repeated or invalid pagination token")
                seen_tokens.add(token)
                params["pageToken"] = token
                params["pageSize"] = min(page_size, per_region - len(region_ids))
            manifest["queries"][region]["selected_count"] = len(region_ids)
            manifest["queries"][region]["selected_study_ids"] = sorted(region_ids)
        manifest["status"] = "complete"
        manifest["completed_at"] = utc_now()
        # Keep separately sourced manual CTRI imports when refreshing CT.gov.
        old_path = root / "processed" / "studies.json"
        if old_path.exists():
            previous = json.loads(old_path.read_text(encoding="utf-8"))
            records.update({s["study_id"]: s for s in previous if s.get("registry") == "CTRI"})
        result = save_dataset(list(records.values()), root, manifest)
        write_json(raw_dir / "manifest.json", result)
        return result
    except Exception as exc:
        manifest.update({"status": "failed", "error": str(exc), "failed_at": utc_now()})
        write_json(raw_dir / "manifest.json", manifest)
        raise
    finally:
        if session is None:
            source_session.close()


def _as_list(value: Any, field: str) -> list:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be a JSON array, including inside CSV cells") from exc
        if isinstance(decoded, list):
            return decoded
    raise ValueError(f"{field} must be a JSON array")


def import_ctri(path: Path, *, root: Path | None = None) -> dict:
    """Import public records manually obtained in compliance with CTRI access rules."""
    root = (root or data_dir()).resolve()
    content = path.read_bytes()
    if len(content) > 20 * 1024 * 1024:
        raise ValueError("CTRI import is limited to 20 MB")
    if path.suffix.lower() == ".json":
        rows = json.loads(content.decode("utf-8-sig"))
    elif path.suffix.lower() == ".csv":
        rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline="")))
    else:
        raise ValueError("Only JSON or CSV imports are supported")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Import must contain a nonempty array/table of records")
    digest = hashlib.sha256(content).hexdigest()
    imported = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Every CTRI row must be an object")
        required = ("study_id", "title", "eligibility_text", "source_url", "retrieved_at", "provenance_note")
        if any(not isinstance(row.get(key), str) or not row[key].strip() for key in required):
            raise ValueError(f"Each CTRI row requires nonempty strings: {', '.join(required)}")
        if not re.fullmatch(r"CTRI/\d{4}/\d{2}/\d{6}", row["study_id"]):
            raise ValueError("Invalid CTRI registration ID")
        url = urlparse(row["source_url"])
        if url.scheme not in ("http", "https") or url.hostname not in ("ctri.nic.in", "www.ctri.nic.in") or not url.path.startswith("/Clinicaltrials/"):
            raise ValueError("source_url must identify a public CTRI record on ctri.nic.in/Clinicaltrials/")
        try:
            timestamp = datetime.fromisoformat(row["retrieved_at"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("timezone missing")
        except ValueError as exc:
            raise ValueError("retrieved_at must be an ISO-8601 timestamp with timezone") from exc
        if row["study_id"] in seen:
            raise ValueError("Duplicate CTRI ID in import")
        seen.add(row["study_id"])
        raw_relative = f"raw/ctri/{digest}{path.suffix.lower()}"
        study = {key: row.get(key) for key in ("study_id", "title", "status", "eligibility_text", "minimum_age", "maximum_age", "sex", "description", "source_url", "last_update", "retrieved_at")}
        study["description"] = study.get("description") or ""
        study.update({key: _as_list(row.get(key), key) for key in ("conditions", "countries", "phase", "locations")})
        if not all(isinstance(country, str) for country in study["countries"]):
            raise ValueError("countries must contain strings")
        if not all(isinstance(location, dict) for location in study["locations"]):
            raise ValueError("locations must contain objects")
        study["countries"] = sorted(set(study["countries"]) | {loc["country"] for loc in study["locations"] if loc.get("country")})
        study["registry"] = "CTRI"
        study["provenance"] = [{"retrieved_at": row["retrieved_at"], "imported_at": utc_now(), "source_url": row["source_url"], "method": "manual_public_record_import", "provenance_note": row["provenance_note"], "raw_file": raw_relative, "sha256": digest}]
        imported.append(study)
    raw_file = root / raw_relative
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    raw_file.write_bytes(content)
    previous_path = root / "processed" / "studies.json"
    previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.exists() else []
    metadata_path = root / "processed" / "study_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    existing = {study["study_id"]: study for study in previous}
    existing.update({study["study_id"]: study for study in imported})
    metadata.setdefault("ctri_imports", []).append({"imported_at": utc_now(), "count": len(imported), "raw_file": raw_relative, "sha256": digest})
    return save_dataset(list(existing.values()), root, metadata)
