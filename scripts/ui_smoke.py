"""Exercise every Streamlit page and principal action against the running API.

Run after scripts/start.ps1. This uses synthetic values only and never approves
clinical criteria. Review persistence/version semantics are tested by test_api.py
with an isolated database.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import requests
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def main():
    requests.get("http://127.0.0.1:8000/health", timeout=10).raise_for_status()
    started = time.perf_counter()
    app = AppTest.from_file(str(ROOT / "frontend/app.py"), default_timeout=60).run()
    actions = []

    def verify(action):
        errors = [e.message for e in app.exception]
        if errors:
            raise AssertionError(f"{action}: {errors}")
        actions.append({"action": action, "status": "passed"})
        print(action + ": passed", flush=True)

    def click(label, timeout=90):
        next(b for b in app.button if b.label == label).click().run(timeout=timeout)
        verify(label)

    for page in list(app.sidebar.radio[0].options):
        app.sidebar.radio[0].set_value(page).run()
        verify("page:" + page)
        if page == "Explore Trials":
            next(s for s in app.selectbox if s.label == "Recruiting-location country").set_value("India").run()
            verify("country_filter")
        elif page == "NLP Laboratory":
            next(r for r in app.radio if r.label == "Input").set_value("Standalone example").run()
            click("Analyze eligibility")
            assert app.session_state["nlp_result"]["transformer"]["status"] == "ok"
            assert app.session_state["nlp_result"]["baseline"]["rules"]
        elif page == "India & US Comparison":
            click("Compare protocols")
        elif page == "Synthetic Evaluation":
            for text in app.text_input:
                if text.label == "Age (years)":
                    text.set_value("35")
            next(c for c in app.checkbox if c.label.startswith("This profile is synthetic")).check()
            click("Evaluate known criteria")
            assert app.session_state["evaluation_result"]["is_synthetic"] is True
        elif page == "Research Assistant":
            next(c for c in app.checkbox if c.label == "Request an experimental local generated draft").check()
            click("Find source evidence", timeout=120)
            result = app.session_state["answer"]
            assert result["evidence"]
            assert all(h["study_id"].startswith("NCT") for h in result["evidence"])
            assert result["generation"]["status"] == "generated_draft"
            assert result["generation"]["verified"] is False
        elif page == "Download Reports":
            for format in ("json", "csv", "html"):
                next(s for s in app.selectbox if s.label == "Report format").set_value(format).run()
                click("Prepare report")
                assert len(app.get("download_button")) == 1
    click("Refresh corpus")
    result = {"run_at_utc": datetime.now(timezone.utc).isoformat(), "method": "Streamlit AppTest against live FastAPI, no mocked HTTP", "actions": actions,
              "status": "passed", "elapsed_seconds": round(time.perf_counter() - started, 3),
              "scope": "All eight pages, country filter, transformer extraction, comparison, synthetic form, hybrid assistant with local generated draft, all three report formats, refresh. Actual browser download click is separate manual QA."}
    (ROOT / "reports/ui_smoke.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
