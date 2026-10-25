# Feature completion and limitations

Status describes observed software behavior; it does not certify scientific or clinical validity.

| Requirement | Status | Evidence / scope |
|---|---|---|
| Supplied prototype audit | VERIFIED | docs/prototype_audit.md; separate legacy command in reports/test_results.json |
| Real API v2 corpus/provenance/normalized tables | VERIFIED | 58 studies, raw hashes, tests/test_ingestion.py, data/processed/study_metadata.json |
| Native CTRI automated access | ACCESS CONSTRAINED | Security-code search observed; zero native CTRI records claimed |
| Permitted CTRI manual JSON/CSV import | VERIFIED | scripts/import_ctri.py; isolated import/provenance tests |
| Classical NLP and supported rules | VERIFIED, NARROW SCOPE | 75 developer references; 18/983 real segments fully parsed; unsupported text retained |
| Real biomedical model inference | VERIFIED | reports/model_smoke.json; live /extract; long-input coverage |
| Published-label entity evaluation | EXPERIMENTAL, EXECUTED | reports/entity_benchmark.json; independent CHIA labels and exact spans |
| Supervised adapted extractor | EXPERIMENTAL, EXECUTED | reports/adaptation_benchmark.json; frozen encoder + trained head; same held-out test |
| Regional comparison | VERIFIED DESCRIPTIVE | Actual paired sources; disjoint country groups, vocabulary/JSD and coverage |
| Regional labeled accuracy/adaptation | SCIENTIFIC BLOCKER | No expert labels for newly retrieved regional study criteria; no learned regional claim |
| Synthetic rule engine and review checkpoint | VERIFIED | Strict synthetic flag, three-valued logic, review hashes/conflicts/revocation tests |
| MiniLM/FAISS/BM25/hybrid retrieval | VERIFIED | 426 source-preserving chunks; actual nine smoke searches and twelve-query ablation |
| Bounded workflow and citations | VERIFIED | Typed tools, six-step limit, source offsets, filter/abstention/injection regressions |
| Local generated draft | EXPERIMENTAL, EXECUTED | reports/generation_smoke.json; incomplete answer retained; no entailment/eligibility claim |
| Optional Ollama provider | ADAPTER TESTED; INFERENCE UNVERIFIED | Configuration and outage tests; no actual Ollama model claimed |
| FastAPI endpoints and eight UI pages | VERIFIED LOCALLY | Active tests, separate live HTTP run and 17 UI actions |
| JSON/CSV/HTML source reports | VERIFIED | Live endpoints/download preparation; source text, unknowns and citations retained |
| Local startup/reuse/shutdown | VERIFIED | Main service health and separate 8100/8601 lifecycle test |
| Dockerfiles and Compose configuration | IMPLEMENTED; CONFIG VERIFIED | docker compose config --quiet exit 0 |
| Docker image build/container startup | EXTERNAL BLOCKER | Actual build exited 1: Docker Desktop engine/socket runtime failure |
| Automated QA | VERIFIED | 150 passed; 0 skipped; legacy independently visible |
| Academic report, demo and viva material | DELIVERED | README.md; docs/technical_report.md/.html; docs/demo_and_viva.md |
| Real-patient/expert clinical validation | UNPERFORMED | Educational synthetic pre-screening only; no clinical authorization or safety claim |

All code is local in this repository. No public hosting URL or external publication is claimed. Models, external corpora, local review databases and credentials are excluded from the safe source checkpoint. Frozen legacy content remains under `legacy/`, outside active pytest discovery, with a separately executed command.
