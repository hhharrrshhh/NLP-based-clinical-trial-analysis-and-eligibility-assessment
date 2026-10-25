"""Eight-page research workspace backed entirely by the FastAPI service."""
import json
import os
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="TrialOps | Protocol Intelligence", page_icon="🧬", layout="wide", initial_sidebar_state="expanded")
API = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
html,body,[class*="css"]{font-family:'DM Sans',sans-serif}
.block-container{padding-top:2rem;max-width:1450px}
[data-testid="stSidebar"]{background:#101f2b;color:#f2f6f7}
[data-testid="stSidebar"] label,[data-testid="stSidebar"] p,[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h3{color:#e5eff3}
[data-testid="stSidebar"] button p{color:#183642}
[data-testid="stMetric"]{background:#edf4f4;border:1px solid #dbe8e9;border-radius:12px;padding:18px}
.hero{background:linear-gradient(110deg,#112b38,#17505c);border-radius:18px;padding:32px;color:white;margin-bottom:24px}
.hero h1{color:white;font-size:2.35rem;margin:0}.hero p{color:#d6e7e8;margin:8px 0 0;font-size:1.05rem}
.eyebrow{color:#a8dcd6;font-size:.76rem;letter-spacing:.17em;font-weight:700;margin-bottom:10px}
button[kind="primary"]{background:#126b70;border:0}
</style>""", unsafe_allow_html=True)


def api(path, payload=None, binary=False):
    try:
        if payload is None:
            response = requests.get(API + path, timeout=(5, 180))
        else:
            response = requests.post(API + path, json=payload, timeout=(5, 180))
        response.raise_for_status()
        return response.content if binary else response.json()
    except requests.RequestException as error:
        details = ""
        if getattr(error, "response", None) is not None:
            try:
                details = str(error.response.json().get("detail", ""))[:600]
            except ValueError:
                pass
        st.error(f"The API request could not finish. {details or 'Check that the backend is running, then retry.'}")
        return None


@st.cache_data(ttl=30)
def corpus():
    return api("/studies")


def study_picker(studies, label="Study", key="study"):
    mapping = {s["study_id"]: s for s in studies}
    if not mapping:
        st.info("No studies match these filters. Ingest public records or change the selection.")
        return None
    return st.selectbox(label, list(mapping), format_func=lambda sid: f"{sid} · {mapping[sid]['title'][:100]}", key=key)


def show_source(study):
    st.markdown(f"**{study['study_id']}** · {(study.get('status') or 'UNKNOWN').replace('_', ' ')}")
    st.write(study["title"])
    st.caption("Sites: " + ", ".join(study.get("countries", [])))
    st.link_button("Open registry source", study["source_url"])
    st.caption(f"Retrieved: {study.get('retrieved_at', 'not supplied')} | Registry updated: {study.get('last_update', 'not supplied')}")


def render_rules(extraction):
    rules = extraction.get("rules", [])
    c1, c2 = st.columns(2)
    c1.metric("Supported rules", len(rules))
    c2.metric("Criteria needing review", len(extraction.get("unresolved", [])))
    if extraction.get("contradictions"):
        st.warning("The extracted source constraints conflict. Review the text and registry metadata before evaluating.")
        st.json(extraction["contradictions"])
    for rule in rules:
        with st.expander(f"{rule['id']} · {rule.get('field', rule.get('logic', 'constraint'))}"):
            st.text(rule.get("source_text", ""))
            st.json(rule)
    if extraction.get("unresolved"):
        with st.expander("Unresolved source criteria", expanded=True):
            st.dataframe(pd.DataFrame(extraction["unresolved"]), use_container_width=True, hide_index=True)


def review_form(extraction, key):
    rules = extraction.get("rules", [])
    if not rules:
        st.info("No supported rules are available to review.")
        return
    st.subheader("Review supported rules")
    st.caption("This records a local review for the synthetic demonstration. It does not certify clinical validity. Rejected or unreviewed rules remain unresolved.")
    with st.form(key):
        chosen = st.multiselect("Rules reviewed against the source", [r["id"] for r in rules], default=[], key=key + "_ids")
        reviewer = st.text_input("Reviewer label", value="demo-reviewer", key=key + "_reviewer")
        decision = st.selectbox("Review decision", ["approved", "rejected"], key=key + "_decision")
        acknowledged = st.checkbox("I compared the selected rules with the original source text.", key=key + "_ack")
        submitted = st.form_submit_button("Save review")
    if submitted:
        if not acknowledged or not chosen or not reviewer.strip():
            st.warning("Select rules, supply a reviewer label, and confirm the source check.")
        else:
            result = api("/reviews", {"study_id": extraction["study_id"], "extraction_hash": extraction["extraction_hash"],
                         "rule_ids": chosen, "decision": decision, "reviewer": reviewer})
            if result:
                st.session_state.pop("evaluation_result", None)
                st.success("Review recorded for this exact extraction version.")
                st.json(result)


with st.sidebar:
    st.title("TrialOps")
    st.caption("ADAPTIVE AI · RESEARCH WORKSPACE")
    page = st.radio("Workspace", ["Overview", "Explore Trials", "NLP Laboratory", "India & US Comparison", "Synthetic Evaluation", "Research Assistant", "Evaluation Dashboard", "Download Reports"])
    st.divider()
    st.caption("Protocol evidence first. Location groups studies; it never changes a clinical cutoff.")
    if st.button("Refresh corpus"):
        corpus.clear()
        st.rerun()
    st.caption("Research prototype · synthetic profiles only")

st.markdown('<div class="hero"><div class="eyebrow">TRIALOPS / PROTOCOL INTELLIGENCE</div><h1>From eligibility text to traceable evidence.</h1><p>Explore real studies. Inspect biomedical NLP. Compare protocols with uncertainty in view.</p></div>', unsafe_allow_html=True)
st.caption("Educational research software. Results concern known criteria only and do not establish study eligibility or medical suitability.")
bundle = corpus()
if bundle is None:
    st.info("Start the FastAPI backend on port 8000, then select Refresh corpus.")
    st.stop()
studies = bundle["studies"]

if page == "Overview":
    st.header("Research overview")
    dashboard = api("/dashboard")
    if dashboard:
        cols = st.columns(4)
        for col, label, value in zip(cols, ["Real studies", "India sites", "US sites", "Shared across regions"],
                                     [dashboard["study_count"], dashboard["regions"].get("India", 0), dashboard["regions"].get("United States", 0), dashboard["overlapping_india_us"]]):
            col.metric(label, value)
        left, right = st.columns([3, 2])
        with left:
            st.subheader("Protocol processing")
            st.bar_chart(pd.DataFrame({"Count": {"Supported rules": dashboard["supported_rule_count"], "Needs review": dashboard["unresolved_criterion_count"], "Approved for demo": dashboard["reviewed_rule_count"]}}), color="#127b80", horizontal=True)
            st.info("A conservative parser leaves temporal, ambiguous, and unsupported clauses for review. Coverage is not extraction accuracy.")
        with right:
            st.subheader("Study status")
            st.dataframe(pd.DataFrame(list(dashboard["statuses"].items()), columns=["Status", "Studies"]), hide_index=True, use_container_width=True)
        st.subheader("Conditions in the retrieved sample")
        st.dataframe(pd.DataFrame(sorted(dashboard["conditions"].items(), key=lambda p: -p[1]), columns=["Condition", "Studies"]), hide_index=True, use_container_width=True)
        st.caption("Convenience sample of registry search results across all statuses. Site-country counts overlap and are not population prevalence estimates.")

elif page == "Explore Trials":
    st.header("Explore clinical trials")
    cols = st.columns(4)
    region = cols[0].selectbox("Recruiting-location country", ["All", "India", "United States"])
    status = cols[1].selectbox("Overall study status", ["All"] + sorted({s.get("status") or "UNKNOWN" for s in studies}))
    condition = cols[2].text_input("Condition contains", value="")
    identifier = cols[3].text_input("Study identifier", value="")
    filtered = [s for s in studies if (region == "All" or region in s.get("countries", [])) and (status == "All" or status == (s.get("status") or "UNKNOWN")) and condition.casefold() in " ".join(s.get("conditions", [])).casefold() and identifier.upper() in s["study_id"].upper()]
    st.caption(f"{len(filtered)} studies match. Country indicates listed sites; current recruitment at an individual site must be checked in the source.")
    selected = study_picker(filtered, key="explore")
    if selected:
        study = next(s for s in filtered if s["study_id"] == selected)
        show_source(study)
        tabs = st.tabs(["Eligibility", "Study description", "Locations", "Provenance"])
        tabs[0].text(study.get("eligibility_text", "No eligibility text supplied."))
        tabs[1].write(study.get("description", "No description supplied."))
        tabs[2].dataframe(pd.DataFrame(study.get("locations", [])), use_container_width=True, hide_index=True)
        tabs[3].json({k: study.get(k) for k in ["registry", "source_url", "retrieved_at", "last_update", "provenance"]})

elif page == "NLP Laboratory":
    st.header("Biomedical NLP laboratory")
    source = st.radio("Input", ["Registry study", "Standalone example"], horizontal=True)
    selected = study_picker(studies, key="nlp") if source == "Registry study" else None
    example = st.text_area("Eligibility statement", value="Participants must be between 18 and 65 years of age and must not have severe renal impairment.", height=150) if source == "Standalone example" else ""
    if selected:
        st.text(next(s["eligibility_text"] for s in studies if s["study_id"] == selected))
    use_transformer = st.checkbox("Run the pretrained biomedical transformer", value=True)
    if st.button("Analyze eligibility", type="primary"):
        with st.spinner("Extracting source-linked rules and biomedical entities…"):
            st.session_state["nlp_result"] = api("/extract", {"study_id": selected, "text": example, "transformer": use_transformer})
    result = st.session_state.get("nlp_result")
    if result and (result["baseline"].get("study_id") == selected or not selected):
        left, right = st.columns(2)
        with left:
            st.subheader("Classical baseline")
            st.dataframe(pd.DataFrame(result["baseline"].get("entities", [])), hide_index=True, use_container_width=True)
        with right:
            st.subheader("Pretrained biomedical NER")
            st.caption(result["transformer"].get("status", "not requested"))
            st.dataframe(pd.DataFrame(result["transformer"].get("entities", [])), hide_index=True, use_container_width=True)
            st.caption("NER detects biomedical spans. Numeric and logical parsing is a separate deterministic component.")
        render_rules(result["baseline"])
        if selected:
            review_form(result["baseline"], "lab_review")

elif page == "India & US Comparison":
    st.header("Compare source protocols")
    left, right = st.columns(2)
    with left:
        india = study_picker([s for s in studies if "India" in s.get("countries", [])], "Study with Indian sites", "india")
    with right:
        usa = study_picker([s for s in studies if "United States" in s.get("countries", [])], "Study with US sites", "usa")
    if india and usa and st.button("Compare protocols", type="primary"):
        result = api("/compare", {"study_ids": [india, usa]})
        if result:
            st.info(result["interpretation"])
            for col, study, extraction in zip(st.columns(2), result["studies"], result["extractions"]):
                with col:
                    show_source(study)
                    st.write("Registry age: ", study.get("minimum_age"), " to ", study.get("maximum_age"))
                    st.text(study.get("eligibility_text", ""))
                    render_rules(extraction)
            st.write("Shared listed conditions:", result["shared_conditions"])
            st.json(result["comparison"], expanded=False)

elif page == "Synthetic Evaluation":
    st.header("Synthetic profile evaluation")
    selected = study_picker(studies, key="evaluation")
    if selected:
        detail = api(f"/studies/{selected}")
        if detail:
            with st.container(border=True):
                st.subheader("Inspect and review extracted rules")
                render_rules(detail["extraction"])
                review_form(detail["extraction"], "evaluation_review")
        with st.form("patient_form"):
            st.caption("Numbers without units use years, kg/m², %, and mmHg. Leave a field blank when unknown. These are fabricated demo values.")
            patient_id = st.text_input("Synthetic profile ID", value="SYN-DEMO-001")
            values = {}
            for col, field, label in zip(st.columns(3), ["age", "bmi", "hba1c"], ["Age (years)", "BMI (kg/m²)", "HbA1c (%)"]):
                values[field] = col.text_input(label, value="", key="p_" + field)
            bp_cols = st.columns(3)
            values["systolic_bp"] = bp_cols[0].text_input("Systolic pressure (mmHg)", value="")
            values["diastolic_bp"] = bp_cols[1].text_input("Diastolic pressure (mmHg)", value="")
            sex = bp_cols[2].selectbox("Sex when protocol requires it", ["Unknown", "MALE", "FEMALE"])
            bools = {}
            for col, field, label in zip(st.columns(3), ["type_2_diabetes", "severe_renal_impairment", "severe_kidney_disease"], ["Type 2 diabetes", "Severe renal impairment", "Severe kidney disease"]):
                bools[field] = col.selectbox(label, ["Unknown", "Yes", "No"])
            for col, field, label in zip(st.columns(3), ["type_1_diabetes", "hypertension", "pregnant"], ["Type 1 diabetes", "Hypertension", "Pregnancy"]):
                bools[field] = col.selectbox(label, ["Unknown", "Yes", "No"])
            synthetic = st.checkbox("This profile is synthetic and contains no real patient data.")
            submitted = st.form_submit_button("Evaluate known criteria", type="primary")
        if submitted:
            if not synthetic:
                st.warning("Confirm that this is a synthetic profile before evaluating.")
            else:
                try:
                    profile = {k: float(v) if v.strip() else None for k, v in values.items()}
                    profile.update({k: {"Unknown": None, "Yes": True, "No": False}[v] for k, v in bools.items()})
                    profile.update(patient_id=patient_id, is_synthetic=True, sex=None if sex == "Unknown" else sex)
                    result = api("/evaluate", {"study_id": selected, "profile": profile})
                    if result:
                        st.session_state["evaluation_result"] = result
                except ValueError:
                    st.warning("Enter valid numbers or leave fields blank.")
        result = st.session_state.get("evaluation_result")
        if result and result.get("study_id") == selected:
            st.subheader(result["status"].replace("_", " ").title())
            st.write(result["explanation"])
            for row in result["rule_results"]:
                with st.expander(f"{row['result']} · {row['rule_id']}"):
                    st.write(row["explanation"])
                    st.json(row)
            st.write("Unresolved requirements", result["unresolved"])
            st.download_button("Download evaluation JSON", json.dumps(result, indent=2), file_name="synthetic_evaluation.json", mime="application/json")

elif page == "Research Assistant":
    st.header("Evidence research assistant")
    st.caption("A bounded workflow retrieves studies, invokes permitted tools, verifies source offsets, and returns a report for review. Source documents cannot issue tool instructions.")
    with st.form("ask_form"):
        question = st.text_area("Research question", value="Which diabetes studies mention BMI restrictions?")
        cols = st.columns(3)
        mode = cols[0].selectbox("Retrieval", ["hybrid", "lexical", "semantic"])
        country = cols[1].selectbox("Country filter", ["Any", "India", "United States"])
        k = cols[2].slider("Evidence chunks", 1, 10, 5)
        generate = st.checkbox("Request an experimental local generated draft")
        submitted = st.form_submit_button("Find source evidence", type="primary")
    if submitted:
        with st.spinner("Searching and verifying evidence…"):
            st.session_state["answer"] = api("/ask", {"question": question, "mode": mode, "country": None if country == "Any" else country, "k": k, "generate": generate})
    result = st.session_state.get("answer")
    if result:
        st.write(result["answer"])
        for hit in result["evidence"]:
            with st.container(border=True):
                st.markdown(f"**{hit['study_id']}** · {hit.get('actual_mode', '')}")
                st.text(hit["text"])
                st.link_button("Verify source", hit["source_url"])
        with st.expander("Workflow trace and typed tool output"):
            st.json({"trace": result["trace"], "tool_result": result.get("tool_result"), "retrieval": result.get("retrieval")})
        generation = result.get("generation", {})
        if generation.get("status") not in {None, "not_requested"}:
            st.warning("Generative draft: " + generation["status"] + ". " + generation.get("reason", ""))
            if generation.get("text"):
                st.text(generation["text"])
                st.caption("Read the source excerpts above before using this draft. Generated claims have not been checked for entailment.")

elif page == "Evaluation Dashboard":
    st.header("Measured experiments")
    result = api("/metrics")
    if result:
        st.info("Published corpus labels, developer reference cases, synthetic tests, and regional descriptive statistics are separate evaluation sources. None establish clinical safety.")
        artifacts = result["artifacts"]
        entity = artifacts.get("entity_benchmark", {})
        if entity.get("metrics"):
            st.subheader("Entity extraction on held-out CHIA documents")
            model_metrics = dict(entity["metrics"])
            adapted = artifacts.get("adaptation_benchmark", {}).get("test")
            if adapted:
                model_metrics["adapted_frozen_encoder_head"] = adapted
            comparison = pd.DataFrame({name: {metric: values[metric] for metric in ("precision", "recall", "f1")} for name, values in model_metrics.items()}).T
            st.bar_chart(comparison, color=["#126b70", "#72aaa7", "#d4a655"], stack=False)
            st.caption("Exact span and mapped category match on 40 documents from 20 study IDs. The dictionary is trained on separate studies. This exploratory corpus transfer comparison does not measure full rule parsing or clinical validity.")
            if adapted:
                st.caption("The adapted head uses 100 training studies; the dictionary uses 800. The comparison does not isolate architecture under equal training data.")
            latency = pd.DataFrame({name: {"Mean latency (ms)": values["mean_inference_latency_ms"]} for name, values in entity["metrics"].items()}).T
            st.bar_chart(latency, horizontal=True, color="#126b70")
        research = artifacts.get("research_metrics", {})
        if research:
            st.subheader("Parser scope and developer references")
            test = research["developer_reference"]["by_split"]["test"]
            columns = st.columns(3)
            score = test["full_rule_match_expected_executable"]
            columns[0].metric("Developer test full match", f"{score['numerator']}/{score['denominator']}")
            unsupported = test["unsupported_abstention"]
            columns[1].metric("Unsupported test abstentions", f"{unsupported['numerator']}/{unsupported['denominator']}")
            profiles = research["synthetic_profile_reference"]["status_accuracy"]
            columns[2].metric("Synthetic status cases", f"{profiles['numerator']}/{profiles['denominator']}")
            groups = research["regional_exploration"]["groups"]
            coverage = pd.DataFrame({name: {"Supported criteria": value["parsed_rules"], "Needs review": value["criteria"] - value["parsed_rules"]} for name, value in groups.items()}).T
            st.bar_chart(coverage, color=["#126b70", "#c4d5d5"], horizontal=True)
            st.caption("Descriptive parser coverage in disjoint site-country groups. Expert regional accuracy is unavailable; shared studies appear once.")
        retrieval = artifacts.get("retrieval_benchmark", {})
        if retrieval.get("metrics"):
            st.subheader("Retrieval ablation")
            values = pd.DataFrame({name: {"Precision@5": row["precision_at_5"], "nDCG@5": row["ndcg_at_5"]} for name, row in retrieval["metrics"].items()}).T
            st.bar_chart(values, color=["#126b70", "#d4a655"], stack=False)
            st.caption("Twelve developer-selected concept queries with explicit heuristic mention labels. These scores do not establish general semantic relevance.")
        if not artifacts:
            st.info("No experiment files yet. Run the documented experiments to generate measurements.")
        for name, artifact in artifacts.items():
            with st.expander(name.replace("_", " ").title(), expanded=False):
                st.json(artifact)
        st.caption("Only actual saved experiment outputs appear here. Missing scores are not shown as zero.")

elif page == "Download Reports":
    st.header("Download source-linked reports")
    selected = study_picker(studies, key="download")
    format = st.selectbox("Report format", ["json", "csv", "html"])
    if selected and st.button("Prepare report", type="primary"):
        content = api(f"/reports/{selected}?format={format}", binary=True)
        if content:
            st.download_button("Download prepared report", content, file_name=f"{selected}.{format}", mime={"json": "application/json", "csv": "text/csv", "html": "text/html"}[format])
    st.caption("HTML reports can be opened in a browser and printed to PDF. Downloads retain evidence, unresolved clauses, source links, and the exact extraction version.")
