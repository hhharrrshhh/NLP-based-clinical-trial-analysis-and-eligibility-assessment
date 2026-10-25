"""UI contract regressions against an isolated real API, without network/model use."""
from pathlib import Path
import pytest
import requests
import streamlit as st
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest
from backend.app import main, services, reviews

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def isolated_ui(monkeypatch, tmp_path):
    fixture = {"study_id": "NCT00000001", "registry": "SYNTHETIC_TEST_FIXTURE", "title": "Synthetic UI fixture, not a registry record",
               "source_url": "https://example.invalid/fixture", "countries": ["India"], "conditions": [], "status": None,
               "eligibility_text": "Age >= 18 years", "minimum_age": "18 Years", "maximum_age": "65 Years", "sex": "ALL"}
    monkeypatch.setattr(main, "get_studies", lambda: [fixture])
    monkeypatch.setattr(services, "get_studies", lambda: [fixture])
    monkeypatch.setattr(services, "get_study", lambda sid: fixture if sid == fixture["study_id"] else None)
    monkeypatch.setattr(reviews, "DATA_DIR", tmp_path)
    client = TestClient(main.app)
    monkeypatch.setattr(requests, "get", lambda url, **kwargs: client.get(url.split(":8000", 1)[1]))
    monkeypatch.setattr(requests, "post", lambda url, json=None, **kwargs: client.post(url.split(":8000", 1)[1], json=json))
    st.cache_data.clear()
    app = AppTest.from_file(str(ROOT / "frontend/app.py"), default_timeout=20).run()
    yield app
    st.cache_data.clear()


def test_null_status_renders_in_explorer(isolated_ui):
    app = isolated_ui
    app.sidebar.radio[0].set_value("Explore Trials").run()
    assert not app.exception
    status = next(s for s in app.selectbox if s.label == "Overall study status")
    assert "UNKNOWN" in status.options
    status.set_value("UNKNOWN").run()
    assert not app.exception


def test_review_change_invalidates_previous_evaluation(isolated_ui):
    app = isolated_ui
    app.sidebar.radio[0].set_value("Synthetic Evaluation").run()
    rules = next(s for s in app.multiselect if s.label == "Rules reviewed against the source")
    rules.set_value(list(rules.options))
    next(c for c in app.checkbox if c.label.startswith("I compared")).check()
    next(b for b in app.button if b.label == "Save review").click().run()
    assert not app.exception
    next(t for t in app.text_input if t.label == "Age (years)").set_value("35")
    next(c for c in app.checkbox if c.label.startswith("This profile is synthetic")).check()
    next(b for b in app.button if b.label == "Evaluate known criteria").click().run()
    assert not app.exception
    assert app.session_state["evaluation_result"]["status"] == "MATCHES_KNOWN_CRITERIA"
    next(s for s in app.selectbox if s.label == "Review decision").set_value("rejected")
    next(b for b in app.button if b.label == "Save review").click().run()
    assert not app.exception
    assert "evaluation_result" not in app.session_state
