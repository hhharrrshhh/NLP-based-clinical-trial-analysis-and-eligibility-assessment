"""Generation abstention and explicit failure without requiring downloaded weights."""
from backend.app.generation import LocalGenerator


def test_empty_evidence_does_not_load_model(monkeypatch):
    generator = LocalGenerator()
    def forbidden():
        raise AssertionError("No evidence must never invoke a model")
    monkeypatch.setattr(generator, "load", forbidden)
    result = generator.generate("Can I join?", [])
    assert result["status"] == "no_evidence"
    assert result["verified"] is False


def test_missing_local_model_is_explicit(monkeypatch):
    generator = LocalGenerator(local_files_only=True)
    def unavailable():
        raise RuntimeError("Model unavailable in test")
    monkeypatch.setattr(generator, "load", unavailable)
    result = generator.generate("What is written?", [{"study_id": "NCT00000001", "text": "source"}])
    assert result["status"] == "unavailable"
    assert result["text"] is None
    assert result["verified"] is False
