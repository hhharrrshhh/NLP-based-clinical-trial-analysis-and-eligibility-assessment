"""Regressions found by an independent review of the integrated application."""
import pytest
from fastapi.testclient import TestClient
from backend.app import main, services, reviews, workflow
from backend.app.retrieval import RetrievalIndex


@pytest.fixture
def synthetic_study(monkeypatch, tmp_path):
    # Deliberately artificial fixture, never written to the real registry corpus.
    study = {"study_id": "NCT00000001", "registry": "SYNTHETIC_TEST_FIXTURE", "title": "Synthetic unit-test fixture",
             "source_url": "https://example.invalid/fixture", "countries": ["India"], "conditions": [],
             "status": None, "eligibility_text": "Age >= 18 years", "minimum_age": "18 Years", "maximum_age": "65 Years", "sex": "ALL"}
    monkeypatch.setattr(main, "get_studies", lambda: [study])
    monkeypatch.setattr(services, "get_studies", lambda: [study])
    monkeypatch.setattr(services, "get_study", lambda sid: study if sid == study["study_id"] else None)
    monkeypatch.setattr(reviews, "DATA_DIR", tmp_path)
    return study


def test_huge_integer_and_nonfinite_rejected(synthetic_study):
    client = TestClient(main.app)
    request = {"study_id": synthetic_study["study_id"], "profile": {"is_synthetic": True, "age": 10**400}}
    assert client.post("/evaluate", json=request).status_code == 422
    raw = '{"study_id":"NCT00000001","profile":{"is_synthetic":true,"age":NaN}}'
    response = client.post("/evaluate", content=raw, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert "NaN" not in response.text


def test_unknown_status_is_filterable(synthetic_study):
    client = TestClient(main.app)
    assert client.get("/studies?status=UNKNOWN").json()["count"] == 1
    assert client.get("/dashboard").json()["statuses"] == {"UNKNOWN": 1}


def test_metadata_conflict_requires_review_before_profile(synthetic_study):
    synthetic_study["maximum_age"] = "17 Years"
    parsed = services.extract_study(synthetic_study["study_id"])
    assert parsed["contradictions"]
    assert parsed["requires_human_validation"]
    reviews.save_review(synthetic_study["study_id"], parsed["extraction_hash"], ["metadata_minimum_age"], "approved", "automated-test")
    result = services.evaluate_study(synthetic_study["study_id"], {"is_synthetic": True, "age": 10})
    assert result["status"] == "INSUFFICIENT_INFORMATION"
    assert result["contradictions"]


def test_id_filter_mismatch_prevents_tool_evaluation(synthetic_study):
    request = main.AskRequest(question="Evaluate NCT00000001 eligibility", country="United States", profile={"is_synthetic": True, "age": 35})
    result = workflow.run_workflow(request)
    assert result["status"] == "ABSTAINED"
    assert result["evidence"] == []
    assert result["tool_result"] is None
    assert all(step["tool"] != "evaluate_synthetic_profile" for step in result["trace"])


def test_pronoun_and_negated_recruitment(synthetic_study, monkeypatch):
    index = RetrievalIndex([synthetic_study], semantic=False)
    monkeypatch.setattr(workflow, "get_index", lambda: index)
    result = workflow.run_workflow(main.AskRequest(question="Show us the diabetes trials", mode="lexical"))
    assert result["interpretation"]["country"] is None
    result = workflow.run_workflow(main.AskRequest(question="Which trials are not currently recruiting?", mode="lexical"))
    assert result["status"] == "ABSTAINED"
    assert result["interpretation"]["status"] is None


def test_exact_id_fallback_provenance_matches_evidence(synthetic_study, monkeypatch):
    index = RetrievalIndex([synthetic_study], semantic=False)
    monkeypatch.setattr(workflow, "get_index", lambda: index)
    result = workflow.run_workflow(main.AskRequest(question="NCT00000001", mode="lexical"))
    assert result["evidence"]
    assert all(hit["actual_mode"] == "exact_id" for hit in result["evidence"])
    assert result["retrieval"]["actual_mode"] == "exact_id"
    assert result["retrieval"]["result_count"] == len(result["evidence"])
