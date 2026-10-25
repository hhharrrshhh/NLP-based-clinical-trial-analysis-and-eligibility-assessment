"""Build the academic report and completion evidence from measured local artifacts."""
from __future__ import annotations
import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import markdown

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8-sig"))


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)] + ["| " + " | ".join(str(x) for x in row) + " |" for row in rows])


def main():
    entity = read("reports/entity_benchmark.json")
    adaptation = read("reports/adaptation_benchmark.json")
    research = read("reports/research_metrics.json")
    retrieval = read("reports/retrieval_benchmark.json")
    tests = read("reports/test_results.json")
    integration = read("reports/integration_smoke.json")
    ui = read("reports/ui_smoke.json")
    deployment = read("reports/deployment.json")
    generation = read("reports/generation_smoke.json")
    metadata = read("data/processed/study_metadata.json")
    studies = read("data/processed/studies.json")
    if hashlib.sha256((ROOT / "data/processed/studies.json").read_bytes()).hexdigest() != research["inputs"]["studies_sha256"]:
        raise ValueError("Registry snapshot differs from the research outputs. Rerun the experiments before generating a report.")
    if len(studies) != integration["study_count"] or len(studies) != retrieval["study_count"]:
        raise ValueError("Experiment and application corpus counts differ; refusing to combine stale artifacts.")
    test = research["developer_reference"]["by_split"]["test"]
    all_references = research["developer_reference"]["all"]
    groups = research["regional_exploration"]["groups"]
    total_criteria = sum(group["criteria"] for group in groups.values())
    supported_criteria = sum(group["parsed_rules"] for group in groups.values())
    rows = [(name, f"{scores['precision']:.4f}", f"{scores['recall']:.4f}", f"{scores['f1']:.4f}", scores["tp"], scores["fp"], scores["fn"])
            for name, scores in adaptation["comparison_with_original_benchmark"]["metrics"].items()]
    entity_table = table(["Model", "Precision", "Recall", "F1", "TP", "FP", "FN"], rows)
    retrieval_table = table(["Mode", "P@5", "Recall@5", "nDCG@5", "Mean ms"],
            [(name, f"{row['precision_at_5']:.4f}", f"{row['recall_at_5']:.4f}", f"{row['ndcg_at_5']:.4f}", f"{row['latency_ms']:.2f}") for name, row in retrieval["metrics"].items()])
    region_table = table(["Disjoint site group", "Studies", "Criterion segments", "Fully parsed", "Coverage"],
            [(name, row["study_count"], row["criteria"], row["parsed_rules"], f"{row['micro_criterion_coverage']['value']:.2%}") for name, row in groups.items()])
    command_table = table(["Verification command group", "Exit code", "Observed status"],
            [(row["name"], row["exit_code"], row["status"]) for row in tests["commands"]])
    report = f'''# TrialOps-Adaptive AI: Academic Technical Report

Cross-Region Clinical Trial Protocol Intelligence and Explainable Eligibility Pre-Screening

**Academic context:** M.Sc. Data Science, NLP Theory + Practical. **Implementation:** Python 3.11, FastAPI, Streamlit, local persistent files and review SQLite. **Verification date:** see the UTC timestamps in the linked experiment artifacts.

## Abstract

This project implements a reproducible clinical-trial protocol reader using {len(studies)} real ClinicalTrials.gov registrations focused on type 2 diabetes, biomedical NER, a conservative rule grammar, source-grounded retrieval and a bounded tool workflow. The prototype evaluates synthetic profiles only. Published CHIA annotations support an exploratory independent entity benchmark; developer-authored references support engineering tests. A supervised frozen-encoder head adaptation was actually trained and evaluated. The system exposes eight working Streamlit pages and a tested FastAPI service.

The main negative findings are low complete-clause parsing coverage on real complex criteria, poor cross-corpus performance of the untouched biomedical model, and incomplete generation from the small local language model. Software behavior is verified locally; these findings do not establish clinical validity, representative regional generalization or eligibility for actual patients.

## 1. Problem, objectives and scope

Unstructured eligibility clauses contain inclusion/exclusion scope, measurements, units, negation, temporal conditions and exceptions. Detecting an entity such as HbA1c does not determine its operator, threshold or logical role. The objectives are source-traceable extraction, deterministic synthetic comparison, bounded retrieval/workflow operations, explicit uncertainty, measured baselines/adaptation, and reproducible deployment.

India and US labels refer to listed study sites. They never introduce population-specific thresholds or substitute for protocol requirements. A study can appear in both descriptive country counts; mutually exclusive groups are used when comparing regional text distributions. There is no real-patient cohort, diagnosis, risk prediction or authorized clinical selection.

## 2. Audit and data collection

The supplied legacy program was read and reproduced: 30 fictional profiles, two fictional protocols, 60 comparisons and four passing original checks. It supplies useful deterministic/missing-value semantics, but no trained model or real protocols. It remains unchanged under `legacy/` and outside active pytest discovery.

The real API v2 collection requested 30 relevance-ranked records from each of India and the US, retained actual listed-location matches, and deduplicated NCT IDs. The result is 58 distinct studies, 32 listing Indian sites, 30 listing US sites, and four listing both. Four response pages and 1,226 location rows were saved. The sample includes seven records with overall status RECRUITING and 39 COMPLETED; presence of a site does not prove that site is currently recruiting. It is a convenience sample across statuses.

Raw response bytes, request URL/parameters, UTC retrieval time, SHA-256 and selected IDs are preserved. Normalized JSON plus studies, criteria and location CSV tables retain source links and last-update fields. Tests verify original criterion text and raw hashes for every shipped study. Pagination, retries/outages, malformed schema and missing optional fields have explicit behavior; a failed run does not silently replace the last good corpus.

CTRI public access inspected during implementation required a security code. No access control was bypassed and zero native CTRI records are claimed. The implemented CSV/JSON manual-import workflow validates real IDs, source hosts, retrieval timestamps and provenance. It supports an authorized human export when available.

CHIA v2 with_scope is a public CC BY 4.0 annotated corpus covering 1,000 studies and 2,000 inclusion/exclusion documents. The exact archive is fingerprinted in the data documentation and reproducible downloader. Original CRLF characters are preserved. Defective annotation/source alignments are excluded and logged rather than guessed. Published annotation labels, developer references, synthetic profiles, unannotated regional documents and predictions remain distinct.

## 3. NLP implementation

The classical pipeline performs NFKC normalization with a map to original offsets, section and sentence/whole-criterion segmentation, tokenization, biomedical abbreviation patterns, entity/numeric/unit recognition and negation/scope parsing. Stopwords are not removed from clinical grammar; meaningful negations and connectives remain. TF-IDF uses normalized unigrams with no stemming or lemmatization so the feature-processing choices do not silently rewrite clinical meaning.

The deterministic grammar supports explicit age, BMI, HbA1c and blood-pressure comparisons, inclusive/exclusive bounds, selected explicit Boolean conditions, AND/OR/NOT, canonical units and documented conversions. A whole criterion is the safety unit: a recognized numeric fragment cannot make a partially understood clause executable. Unsupported temporal wording, qualifiers, ambiguous shared scope, malformed measurements and unsupported terminology remain NEEDS_REVIEW.

The real pretrained model is `d4data/biomedical-ner-all` at a pinned revision, loaded with safetensors and remote code disabled. It processes all tokens using overlapping 512-token windows rather than silently truncating protocols. Output consists of exact original entity spans, labels and model scores. NER never authorizes a clinical rule. The model's clinical-case-report training domain and ontology differ from trial eligibility annotation.

## 4. Rule review and synthetic evaluation

Structured source age/sex fields supplement text parsing. Their constraints are included in extraction fingerprints and conflict checks. A supported-grammar flag denotes syntactic/semantic recognition within the declared grammar; it is not expert approval. The application executes study rules only after a separate local synthetic-demo review bound to the exact extraction hash and rule IDs.

Reviews persist in SQLite with decision, reviewer label, scope and time. These local labels are unauthenticated and do not establish clinician identity. Changed source semantics invalidate old approval versions. Changing a review clears any saved UI evaluation so a revoked approval cannot leave a stale matching result visible. Source conflicts remain blocking until conflicting interpretations are resolved/rejected.

Evaluation uses TRUE/FALSE/UNKNOWN. Missing observations are unknown, and a positive diagnosis list does not establish negative findings. AND/OR/NOT preserve uncertainty. The statuses are MATCHES_KNOWN_CRITERIA, DOES_NOT_MATCH_KNOWN_CRITERIA, and INSUFFICIENT_INFORMATION. Even a known-criteria match does not prove complete protocol eligibility; source and unresolved requirements remain visible.

## 5. Independent entity benchmark and actual adaptation

The entity experiment maps CHIA Condition/Drug/Procedure to a documented subset of the pretrained model's labels. Exact category and character-span agreement is required; discontinuous gold spans remain in evaluation. Twenty held-out study IDs supply 40 documents and 328 gold entities. A dictionary learns only from 800 separate training studies. This is a fixed exploratory test subset, not an official benchmark split; shared upstream training exposure cannot be ruled out.

{entity_table}

The adapted model freezes the entire biomedical encoder and trains only a new 5,383-parameter seven-label BIO head. It uses 100 training studies and 20 separate development studies, with the same original 20 test studies held out until epoch selection. Class-weighted token cross-entropy trains the head; epoch 8 is selected by development exact-span F1. Training loss decreased from 1.239686 to 0.735666. Ignored ambiguous supervision is documented; full mapped gold still counts in test scoring.

The head run took {adaptation['performance']['total_seconds_including_load_encoding_training_evaluation']:.2f} seconds including loading, frozen encoding, training and evaluation; sampled peak process RSS was {adaptation['performance']['sampled_peak_process_rss_mib']:.2f} MiB. These are CPU observations on this machine. This is supervised head adaptation, not end-to-end fine-tuning or learned India/US adaptation. The dictionary used more labeled training studies, so architecture is not isolated under equal training volume. The head improves over the untouched transformer but remains below the dictionary. No statistical significance or general superiority is inferred.

![Entity model comparison](../reports/adaptation_comparison.png)

![Actual adaptation learning curve](../reports/adaptation_learning_curve.png)

## 6. Parser, rule and regional experiments

There are 75 static developer-authored semantic reference cases: 45 expected executable and 30 unsupported. Labels were independently specified as field/operator/value/unit/type/negation/logical signatures, not generated from predictions. They are neither blinded nor expert clinical annotations. Source families remain together in train/dev/test bookkeeping splits, with no parser training or modification against these outcomes.

The developer TEST split has 20 cases: 12 supported and eight unsupported. Full supported-case signature match is {test['full_rule_match_expected_executable']['numerator']}/{test['full_rule_match_expected_executable']['denominator']} ({test['full_rule_match_expected_executable']['value']:.1%}). Confusion counts are TP=10, FP=0, TN=8, FN=2; FPR=0/8 and FNR=2/12. Test abstention is 10/20. Pooled full supported-case fidelity is 43/45, which must not be substituted for the held-out result. The two missed lexical formulations remain documented and unchanged. Zero false positives in eight selected test cases is not a clinical safety guarantee.

Eighteen additional authored synthetic profile scenarios produce {research['synthetic_profile_reference']['status_accuracy']['numerator']}/{research['synthetic_profile_reference']['status_accuracy']['denominator']} expected statuses, covering boundaries, missingness, negation, exclusions, AND/OR, units and contradictions. These are software-behavior labels, not patient outcomes.

{region_table}

Overall real-corpus complete criterion coverage is {supported_criteria}/{total_criteria} ({supported_criteria/total_criteria:.2%}); all 58 studies retain unresolved requirements. This deliberately strict figure is coverage, not accuracy. Registry metadata rules are additional structured constraints and are not counted as successful text parsing. Human regional accuracy is unavailable because the newly retrieved studies have no independent expert labels.

The regional study split is deterministic by study ID, with 49 training and nine test studies. Shared India/US studies appear once in a separate group. The 2,190-term TF-IDF vocabulary is fit only on training text. Overall India-only/US-only unigram JSD is 0.202595; the tiny test subset (three India-only, six US-only studies) gives 0.395537. These descriptive values do not show clinical population differences, causal effects or learned adaptation. Exact duplicate text is audited, but related sponsor/protocol families are not fully clustered.

![Parser and regional measurements](../reports/research/regional_coverage.png)

## 7. Retrieval, workflow and generation

Sentence Transformers `all-MiniLM-L6-v2` supplies 384-dimensional embeddings. FAISS uses normalized inner product, BM25 supplies lexical retrieval, and reciprocal-rank fusion combines ranks. The current index contains 426 exact source chunks with IDs, URLs, fields and offsets. Context windowing preserves coverage; model/corpus fingerprints and checksums protect stale/corrupt local artifacts. Runtime avoids untrusted pickle or native FAISS deserialization. Model failure is explicitly reported as fallback, not advertised as semantic success.

{retrieval_table}

These scores average twelve predeclared developer-selected concept queries with exhaustive heuristic term-mention qrels. They are not independent human semantic-relevance judgments. Mentions can be negated or merely contextual; relevance labels do not establish executable requirements. Confidence intervals are omitted because the concepts are deliberately chosen and nonrepresentative.

![Measured retrieval ablation](../reports/experiments/retrieval_ablation.png)

The bounded workflow is a typed finite-state equivalent to a graph orchestrator: interpret query; retrieve/extract/compare/evaluate through permitted functions; verify exact evidence offsets; compile a source-linked report and review checkpoint. It has a six-step limit, explicit abstention and no execution of document instructions. Filtering occurs before a typed study evaluation. Exact-ID retrieval reports its actual fallback mode. It is not an autonomous clinical reasoning agent.

Local `google/flan-t5-small`, a pinned Apache-2.0 77M-parameter model, actually generated a draft on CPU. The measured real-source output was **{generation['result'].get('text', 'No output')}** for a question asking for the explicit HbA1c requirement. This is incomplete and is retained as a negative finding. Inference execution is successful; answer correctness is not established. The draft is optional, unverified, limited to selected source context, and never used by the rule engine. Numeric-token checks do not prove entailment. Primary responses retain verified source excerpts. An optional Ollama adapter handles configured servers and tested outages; no actual Ollama inference is claimed.

## 8. Engineering and verification

The FastAPI application provides strict Pydantic requests, byte/text limits, CORS allowlists, network timeouts, safe source/report handling and explicit failures. Invalid requests do not echo profile payloads. The Streamlit frontend provides all eight requested workspaces. Local files, persisted index artifacts and SQLite keep the architecture small. All demonstration profiles are fabricated.

{command_table}

The saved active pytest run reports {tests['pytest']['passed']} passed, {tests['pytest']['failures']} failures, {tests['pytest']['errors']} errors, and {tests['pytest']['skipped']} skipped. Source code is fingerprinted and unchanged during that verification run: `{tests['source_sha256']}`. Legacy checks run separately and remain visible. Live HTTP integration status is {integration['status']}; the UI harness reports {len(ui['actions'])} successful page/action checks against the live backend. Tests also exercise isolated UI review approval/revocation and unknown-status records.

Measured regression fixes include stale evaluation invalidation on review changes, rejecting huge/nonfinite measurements cleanly, preserving unknown status semantics, merged metadata/text contradiction checks, exact-ID filter enforcement, consistent retrieval provenance, and preventing 'show us' or 'not currently recruiting' from silently becoming positive US/recruiting filters. Source-injection tests prove the workflow cannot convert retrieved text into tool instructions; they do not constitute a general language-model safety certification.

## 9. Deployment and blockers

Local FastAPI and Streamlit health checks pass at http://127.0.0.1:8000 and http://127.0.0.1:8501. PowerShell startup, existing-service reuse, owned-process shutdown and isolated-port startup/shutdown were exercised. JSON/CSV/HTML reports preserve evidence and unknowns. There is no public deployment or production clinical authorization.

Dockerfiles, Compose networking, local-only published ports, non-root users, health checks and persistent data/model mounts are implemented. Compose configuration validates. The actual build attempted on this machine failed before an image build because the installed Docker Desktop Linux engine pipe is missing. Starting Desktop revealed an inaccessible `dockerInference` socket rename in its backend log. No container build/start success is claimed. The exact evidence is in `reports/deployment.json`; resolving that local Docker runtime problem and rerunning the commands remains an external deployment blocker.

## 10. Threats to validity and ethics

The real registry sample is small, nonrandom, multilingual metadata can vary, and source records can change. Sponsor-submitted records are not independently clinically verified. The parser's narrow grammar has very low real-protocol coverage. Developer references are selected and nonblinded; ontology mapping, span defects and one held-out CHIA subset limit entity conclusions. Model pretraining leakage cannot be fully audited. Head training uses one seed and a smaller training set than the dictionary. Retrieval qrels are lexical heuristics. CPU/RSS measurements are local process observations, not deployment guarantees or exclusive per-model memory. Softmax and cosine scores are not calibrated clinical probabilities.

No actual patients are processed or selected. Country never changes source thresholds. Missing observations and unsupported semantics remain unknown. Local review labels do not replace expert validation. The generated model is limited and can produce incomplete or unsupported prose; citations verify quoted bytes, not entailment of generated statements. A real application would require independent clinician review, privacy/access governance, clinical validation and appropriate authorization.

## 11. Reproduction, further research and references

Use the README and `docs/deployment.md` for exact Windows/Compose commands. Download the fingerprinted CHIA archive, run the three entity/research/retrieval experiments and model/generation smoke scripts, start services, then run `python -m scripts.verify --live`. Regenerate this report with `python -m scripts.build_documentation`. Raw predictions, splits, exclusions, CSV results, checksums and plots are retained for independent review. Model weights and downloaded external corpora are excluded from Git and the release archive.

Independent expert regional annotation, protocol-family-aware sampling, multi-reviewer agreement, multiple random seeds, equal-data architecture comparisons, stronger temporal/scope parsing, calibrated abstention and a higher-quality entailment-checked generation backend are future work. Learned regional adaptation remains unperformed because comparable regional gold is unavailable.

- ClinicalTrials.gov. [API v2 documentation](https://clinicaltrials.gov/data-api/api) and [terms](https://clinicaltrials.gov/about-site/terms-conditions).
- Kury et al. (2020). [Chia, a large annotated corpus of clinical trial eligibility criteria](https://doi.org/10.1038/s41597-020-00620-0). [Annotated dataset v2](https://doi.org/10.6084/m9.figshare.11855817.v2), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- [MACCROBAT dataset](https://figshare.com/articles/dataset/MACCROBAT2018/9764942), inspected for access/license; not imported as a patient cohort.
- [Biomedical NER model card](https://huggingface.co/d4data/biomedical-ner-all), [MiniLM model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2), [FLAN-T5-small model card](https://huggingface.co/google/flan-t5-small).
- CTRI. [Official registry search](https://ctri.nic.in/Clinicaltrials/advancesearchmain.php); compliant manual import only.

Source methods, attribution and exact revisions are expanded in `docs/data_sources.md`, `docs/models.md`, `docs/adaptation.md`, `docs/annotation_workflow.md` and the raw JSON experiment reports. No publication-level or clinical validation is implied by the software deliverable.
'''
    docs = ROOT / "docs"
    # Use the actual generated research chart filenames instead of guessing them.
    charts = sorted((ROOT / "reports/research").glob("*.png"))
    if charts:
        report = report.replace("../reports/research/regional_coverage.png", "../" + charts[-1].relative_to(ROOT).as_posix())
    (docs / "technical_report.md").write_text(report, encoding="utf-8")
    body = markdown.markdown(report, extensions=["tables", "fenced_code"])

    def inline_image(match):
        path = (docs / match[1]).resolve()
        if not path.is_relative_to(ROOT) or not path.exists():
            raise ValueError(f"Report image not found: {path}")
        return 'src="data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode() + '"'

    body = re.sub(r'src="(\.\./reports/[^\"]+\.png)"', inline_image, body)
    page = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>TrialOps Academic Technical Report</title><style>
    body{font:16px/1.65 system-ui,sans-serif;color:#17353e;background:#edf3f4;margin:0}main{max-width:1060px;margin:32px auto;background:white;padding:48px 64px;border-radius:16px}h1{font-size:2.2rem;line-height:1.2;color:#123743}h2{margin-top:2.2em;color:#126b70}table{border-collapse:collapse;width:100%;font-size:.9em;margin:20px 0}th{background:#e6f0f1;text-align:left}td,th{border:1px solid #d7e4e5;padding:9px;vertical-align:top}a{color:#126b70}pre,code{background:#eef4f4;overflow-wrap:anywhere}pre{padding:18px;white-space:pre-wrap}img{max-width:100%;height:auto}li{margin:8px 0}@media(max-width:720px){main{padding:22px;margin:0;border-radius:0}table{display:block;overflow-x:auto}}@media print{body{background:white;font-size:10pt}main{margin:0;padding:0;max-width:none}h2{break-after:avoid}img,table{break-inside:avoid}a{color:inherit}}
    </style></head><body><main>''' + body + "</main></body></html>"
    (docs / "technical_report.html").write_text(page, encoding="utf-8")

    feature_rows = [
        ("Supplied prototype audit", "VERIFIED", "docs/prototype_audit.md; separate legacy command in reports/test_results.json"),
        ("Real API v2 corpus/provenance/normalized tables", "VERIFIED", "58 studies, raw hashes, tests/test_ingestion.py, data/processed/study_metadata.json"),
        ("Native CTRI automated access", "ACCESS CONSTRAINED", "Security-code search observed; zero native CTRI records claimed"),
        ("Permitted CTRI manual JSON/CSV import", "VERIFIED", "scripts/import_ctri.py; isolated import/provenance tests"),
        ("Classical NLP and supported rules", "VERIFIED, NARROW SCOPE", "75 developer references; 18/983 real segments fully parsed; unsupported text retained"),
        ("Real biomedical model inference", "VERIFIED", "reports/model_smoke.json; live /extract; long-input coverage"),
        ("Published-label entity evaluation", "EXPERIMENTAL, EXECUTED", "reports/entity_benchmark.json; independent CHIA labels and exact spans"),
        ("Supervised adapted extractor", "EXPERIMENTAL, EXECUTED", "reports/adaptation_benchmark.json; frozen encoder + trained head; same held-out test"),
        ("Regional comparison", "VERIFIED DESCRIPTIVE", "Actual paired sources; disjoint country groups, vocabulary/JSD and coverage"),
        ("Regional labeled accuracy/adaptation", "SCIENTIFIC BLOCKER", "No expert labels for newly retrieved regional study criteria; no learned regional claim"),
        ("Synthetic rule engine and review checkpoint", "VERIFIED", "Strict synthetic flag, three-valued logic, review hashes/conflicts/revocation tests"),
        ("MiniLM/FAISS/BM25/hybrid retrieval", "VERIFIED", "426 source-preserving chunks; actual nine smoke searches and twelve-query ablation"),
        ("Bounded workflow and citations", "VERIFIED", "Typed tools, six-step limit, source offsets, filter/abstention/injection regressions"),
        ("Local generated draft", "EXPERIMENTAL, EXECUTED", "reports/generation_smoke.json; incomplete answer retained; no entailment/eligibility claim"),
        ("Optional Ollama provider", "ADAPTER TESTED; INFERENCE UNVERIFIED", "Configuration and outage tests; no actual Ollama model claimed"),
        ("FastAPI endpoints and eight UI pages", "VERIFIED LOCALLY", "Active tests, separate live HTTP run and 17 UI actions"),
        ("JSON/CSV/HTML source reports", "VERIFIED", "Live endpoints/download preparation; source text, unknowns and citations retained"),
        ("Local startup/reuse/shutdown", "VERIFIED", "Main service health and separate 8100/8601 lifecycle test"),
        ("Dockerfiles and Compose configuration", "IMPLEMENTED; CONFIG VERIFIED", "docker compose config --quiet exit 0"),
        ("Docker image build/container startup", "EXTERNAL BLOCKER", "Actual build exited 1: Docker Desktop engine/socket runtime failure"),
        ("Automated QA", "VERIFIED", f"{tests['pytest']['passed']} passed; {tests['pytest']['skipped']} skipped; legacy independently visible"),
        ("Academic report, demo and viva material", "DELIVERED", "README.md; docs/technical_report.md/.html; docs/demo_and_viva.md"),
        ("Real-patient/expert clinical validation", "UNPERFORMED", "Educational synthetic pre-screening only; no clinical authorization or safety claim"),
    ]
    matrix = "# Feature completion and limitations\n\nStatus describes observed software behavior; it does not certify scientific or clinical validity.\n\n" + table(["Requirement", "Status", "Evidence / scope"], feature_rows)
    matrix += "\n\nAll code is local in this repository. No public hosting URL or external publication is claimed. Models, external corpora, local review databases and credentials are excluded from the safe source checkpoint. Frozen legacy content remains under `legacy/`, outside active pytest discovery, with a separately executed command.\n"
    (docs / "feature_completion.md").write_text(matrix, encoding="utf-8")
    audit = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "source_sha256": tests["source_sha256"],
             "software_verification": tests["status"], "live_integration": integration["status"], "live_ui": ui["status"],
             "scientific_validation": "Exploratory measurements; regional expert labels and clinical validation unavailable",
             "docker": deployment["docker"]["status"], "items": [{"requirement": a, "status": b, "evidence": c} for a, b, c in feature_rows]}
    (ROOT / "reports/completion_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print("Generated technical_report.md, self-contained technical_report.html, feature_completion.md and completion_audit.json from measured artifacts.")


if __name__ == "__main__":
    main()
