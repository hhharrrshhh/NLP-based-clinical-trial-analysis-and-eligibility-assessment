"""Synthetic HTTP fixtures test plumbing; the shipped corpus is real API data."""
import csv
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from backend.app.ingestion import IngestionError, fetch_page, import_ctri, ingest, normalize_study
from backend.app.store import get_studies, get_study


def source_study(number=1, countries=("India",)):
    return {"protocolSection": {
        "identificationModule": {"nctId": f"NCT{number:08d}", "briefTitle": "Synthetic HTTP test fixture, not real study data"},
        "eligibilityModule": {"eligibilityCriteria": "Inclusion Criteria:\nAge >= 18 years", "minimumAge": "18 Years"},
        "contactsLocationsModule": {"locations": [{"country": country} for country in countries]},
    }}


def response(payload=None, status=200):
    result = requests.Response()
    result.status_code = status
    result.url = "https://clinicaltrials.gov/api/v2/studies?test_fixture=true"
    result._content = json.dumps(payload if payload is not None else {}).encode()
    return result


def test_normalize_preserves_multicountry_and_unknowns():
    study = normalize_study(source_study(countries=("India", "United States")), {"retrieved_at": "2026-10-17T00:00:00Z"})
    assert study["countries"] == ["India", "United States"]
    assert study["minimum_age"] == "18 Years"
    assert study["maximum_age"] is None
    assert study["status"] is None
    assert study["phase"] == []
    assert study["source_url"].endswith("NCT00000001")


@pytest.mark.parametrize("raw", [{}, {"protocolSection": []}, {"protocolSection": {"identificationModule": {"nctId": "invented"}}}, {"protocolSection": {"identificationModule": {"nctId": "NCT00000001"}, "contactsLocationsModule": {"locations": ["bad"]}}}])
def test_schema_change_rejected(raw):
    with pytest.raises(IngestionError):
        normalize_study(raw, {"retrieved_at": "2026-10-17T00:00:00Z"})


def test_retry_timeout_and_server_error():
    session = Mock()
    session.get.side_effect = [requests.Timeout("temporary"), response(status=503), response({"studies": []})]
    sleep = Mock()
    assert fetch_page(session, {}, sleep=sleep).status_code == 200
    assert session.get.call_count == 3
    assert sleep.call_count == 2


def test_forbidden_is_not_retried():
    session = Mock()
    session.get.return_value = response(status=403)
    with pytest.raises(IngestionError, match="HTTP 403"):
        fetch_page(session, {}, sleep=Mock())
    assert session.get.call_count == 1


def test_network_outage_exhausts_bounded_retry():
    session = Mock()
    session.get.side_effect = requests.ConnectionError("offline")
    with pytest.raises(IngestionError, match="after 4 attempts"):
        fetch_page(session, {}, sleep=Mock())
    assert session.get.call_count == 4


def test_paginate_deduplicate_and_preserve_provenance(tmp_path, monkeypatch):
    session = Mock()
    session.get.side_effect = [
        response({"studies": [source_study(1)], "nextPageToken": "second", "totalCount": 2}),
        response({"studies": [source_study(2, ("India", "United States"))]}),
        response({"studies": [source_study(2, ("India", "United States"))], "nextPageToken": "us_second", "totalCount": 2}),
        response({"studies": [source_study(3, ("United States",))]}),
    ]
    result = ingest(2, root=tmp_path, page_size=1, session=session)
    assert result["study_count"] == 3
    assert result["india_us_overlap"] == 1
    assert len(result["pages"]) == 4
    for page in result["pages"]:
        assert hashlib.sha256((tmp_path / page["raw_file"]).read_bytes()).hexdigest() == page["sha256"]
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert len(get_studies()) == 3
    assert len(get_study("NCT00000002")["provenance"]) == 2
    assert get_study("missing") is None
    assert get_study("NCT00000002")["countries"] == ["India", "United States"]
    for name in ("studies.csv", "eligibility_criteria.csv", "study_locations.csv", "study_metadata.json", "studies.json"):
        assert (tmp_path / "processed" / name).is_file()


def test_empty_page_with_token_continues(tmp_path):
    session = Mock()
    session.get.side_effect = [response({"studies": [], "nextPageToken": "continue"}), response({"studies": [source_study()]}), response({"studies": []})]
    assert ingest(1, root=tmp_path, session=session)["study_count"] == 1


def test_repeated_page_token_fails_without_overwriting_corpus(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    path = processed / "studies.json"
    path.write_text("[]")
    session = Mock()
    session.get.side_effect = [response({"studies": [], "nextPageToken": "repeated"}), response({"studies": [], "nextPageToken": "repeated"})]
    with pytest.raises(IngestionError, match="pagination token"):
        ingest(1, root=tmp_path, session=session)
    assert path.read_text() == "[]"
    manifest = json.loads(next((tmp_path / "raw").rglob("manifest.json")).read_text())
    assert manifest["status"] == "failed"


def test_response_schema_change(tmp_path):
    session = Mock()
    session.get.return_value = response({"results": []})
    with pytest.raises(IngestionError, match="studies array"):
        ingest(1, root=tmp_path, session=session)


def ct_record():
    return {"study_id": "CTRI/2026/01/000001", "title": "Synthetic import validation fixture", "eligibility_text": "Synthetic test only.", "source_url": "https://ctri.nic.in/Clinicaltrials/showallp.php?trialid=000001", "retrieved_at": "2026-10-17T00:00:00Z", "provenance_note": "Synthetic unit test fixture, never included in real corpus.", "countries": ["India"]}


def test_ctri_manual_import_and_provenance(tmp_path):
    path = tmp_path / "records.json"
    path.write_text(json.dumps([ct_record()]))
    result = import_ctri(path, root=tmp_path / "data")
    assert result["registry_counts"] == {"CTRI": 1}
    provenance = result["record_provenance"][ct_record()["study_id"]][0]
    assert provenance["method"] == "manual_public_record_import"
    assert (tmp_path / "data" / provenance["raw_file"]).is_file()
    assert provenance["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_ctri_csv_preserves_multiline_criteria(tmp_path):
    row = ct_record()
    row["eligibility_text"] = "Inclusion criteria:\nSynthetic multiline test only."
    row["countries"] = json.dumps(row["countries"])
    path = tmp_path / "records.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    import_ctri(path, root=tmp_path / "data")
    actual = json.loads((tmp_path / "data/processed/studies.json").read_text())
    assert actual[0]["eligibility_text"] == row["eligibility_text"]


@pytest.mark.parametrize("changes", [{"source_url": "https://evil.example/Clinicaltrials/1"}, {"source_url": "https://ctri.nic.in.evil.example/Clinicaltrials/1"}, {"study_id": "NCT00000001"}, {"retrieved_at": "2026-10-17"}, {"provenance_note": ""}, {"conditions": "Diabetes"}, {"countries": [42]}])
def test_ctri_invalid_provenance_rejected(tmp_path, changes):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([{**ct_record(), **changes}]))
    with pytest.raises(ValueError):
        import_ctri(path, root=tmp_path / "data")
    assert not (tmp_path / "data" / "processed").exists()


def test_shipped_corpus_real_source_integrity():
    root = Path(__file__).resolve().parents[1] / "data"
    studies = json.loads((root / "processed" / "studies.json").read_text(encoding="utf-8"))
    assert len(studies) >= 50
    assert len({study["study_id"] for study in studies}) == len(studies)
    assert all(study["eligibility_text"] and study["provenance"] for study in studies)
    for study in studies:
        assert study["registry"] in ("ClinicalTrials.gov", "CTRI")
        for provenance in study["provenance"]:
            assert hashlib.sha256((root / provenance["raw_file"]).read_bytes()).hexdigest() == provenance["sha256"]
        if study["registry"] == "ClinicalTrials.gov":
            raw = json.loads((root / study["provenance"][0]["raw_file"]).read_text(encoding="utf-8"))
            original = next(record for record in raw["studies"] if record["protocolSection"]["identificationModule"]["nctId"] == study["study_id"])
            assert original["protocolSection"]["eligibilityModule"]["eligibilityCriteria"] == study["eligibility_text"]
