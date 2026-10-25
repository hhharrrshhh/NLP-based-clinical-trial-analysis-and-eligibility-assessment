# Professor demonstration and viva notes

## Six-minute live demonstration

1. Start with `scripts/start.ps1`; open `http://127.0.0.1:8501`. State that this is a research protocol reader using fabricated profiles, and country groups studies without changing source thresholds.
2. Overview: show 58 real studies, 32 India-site records, 30 US-site records, and four shared. Explain why counts overlap and why all statuses are retained. Show unresolved text rather than presenting coverage as accuracy.
3. Explore Trials: filter India and inspect NCT00261352. Open its actual registry link and original eligibility/provenance. Show that native CTRI automated data is not claimed; the permitted manual import is documented.
4. NLP Laboratory: run the pretrained transformer on the selected source, then analyze the standalone educational sentence `Participants must be between 18 and 65 years of age and must not have severe renal impairment.` Explain source spans, logical conditions and the separate NER/parser roles. Add an unsupported temporal clause and show abstention.
5. Compare the India-site source with US-site NCT00081328. The latter is the real TODAY adolescent/youth study. Inspect its actual registry age fields and eligibility. Compare these two protocols without claiming national medical standards.
6. Synthetic Evaluation: select NCT00081328 and enter a fabricated age of 35. First show insufficient information while supported rules await review. Inspect the source maximum-age field and approve that rule for the synthetic demonstration using your own reviewer label. Re-evaluate: a known age mismatch can be shown, while all unresolved requirements remain visible. Change the review decision and demonstrate that the previous result is cleared. This is a demo of rule behavior, not actual patient selection.
7. Research Assistant: ask `Which diabetes studies mention BMI restrictions?` using hybrid search. Read the exact source text and workflow trace. Optional generated drafts are explicitly unverified; the tested small model produced an incomplete answer. Do not present its prose as clinical reasoning.
8. Evaluation Dashboard: show dictionary/pretrained/adapted entity results, conservative real-corpus parsing coverage, and the retrieval ablation. Open the stored per-case outputs and explain the distinct label sources. Download a source-linked JSON or HTML report.

If a live source/model request fails, show its explicit failure state and the already saved timestamped experiment artifacts. Do not replace it with invented outputs or describe a saved report as a newly completed run.

## Short presentation outline

| Slide | Content and evidence |
|---|---|
| 1. Research problem | Unstructured trial criteria, missing information and traceable explanations |
| 2. Actual data | API v2, 58 studies, overlapping sites, source hashes, CTRI limitation |
| 3. NLP design | Entity detection versus complete-clause numeric/logical parsing; uncertainty |
| 4. Synthetic rule engine | Three-valued logic, source-based thresholds, review versions and conflicts |
| 5. ML experiments | Published CHIA labels, study splits, dictionary/pretrained/head-adaptation comparison |
| 6. Negative findings | Low real criterion coverage, two developer lexical misses, limited generation |
| 7. Retrieval and application | BM25/MiniLM/FAISS ablation, bounded typed workflow and eight pages |
| 8. Verification and limits | Actual test evidence, local deployment, Docker engine blocker, expert validation still required |

Use the generated technical report and stored plots for the actual figures. This outline is not a separately created slide deck.

## Viva questions and answers

**What makes the work more than the supplied prototype?** Real registry ingestion/provenance, executed biomedical inference, structured text parsing, review-bound evaluation, source-preserving hybrid retrieval, actual ML experiments, API/UI integration and reproducible tests. The old prototype used two fictional protocols only.

**Does selecting India change BMI or HbA1c thresholds?** No. Only the selected protocol's explicit requirements supply thresholds. Site location does not determine ethnicity, nationality or medical suitability.

**Why is NER not enough?** A detected measurement/entity does not encode its comparator, units, exclusion role, temporal scope, exceptions or Boolean relationships. These require separately validated semantics.

**What was actually trained?** A 5,383-parameter linear seven-label BIO head on frozen biomedical DistilBERT features, using 100 CHIA training studies and 20 development studies. The encoder was not fine-tuned. Development F1 selected epoch 8 before the original test set was evaluated.

**What is the measured model result?** Exact entity F1 on the same 20 studies/40 documents/328 mapped gold spans is 0.4253 for the training dictionary, 0.1265 for the untouched biomedical transformer, and 0.3212 for the adapted head. The dictionary saw 800 training studies; comparisons do not isolate architecture under equal data volume.

**Why did the transformer lose to a dictionary?** Strict span boundaries, label-ontology differences and clinical-case-report versus trial-criteria domain mismatch matter. This exploratory subset does not establish universal dictionary superiority.

**Is this learned India/US domain adaptation?** No. Regional coverage, TF-IDF and JSD are descriptive. The real trained experiment adapts a head to CHIA labels. Comparable independently labeled regional criteria are unavailable.

**How are source leakage and split leakage addressed?** Raw-source hashes and exact offsets establish provenance. CHIA includes/excludes stay grouped by study. Test IDs/text hashes/gold are checked against the original benchmark. Regional study IDs are disjoint, although sponsor/protocol-family or upstream pretraining leakage cannot be fully ruled out.

**What do the parser scores mean?** The developer test split matched 10/12 supported semantic references and abstained on 8/8 unsupported examples. Labels are selected developer references, not blinded clinical gold. Real-source complete criterion coverage is only 18/983, a separate measure.

**Does zero false positives mean the system is safe?** No. The denominator is eight selected unsupported developer test cases. Broader independent annotation and clinical validation would be needed to estimate real error rates.

**Why is real parsing coverage low?** The grammar is intentionally narrow and only compiles fully understood clauses. Real protocols contain many unsupported temporal, medication, laboratory, nested-scope and investigator-judgment requirements. Those stay unresolved instead of being partially executed.

**What does a missing diagnosis mean?** Unknown. An omitted condition or absence from a positive diagnosis list is not evidence that the condition is absent. Explicit true/false observations are needed for Boolean comparisons.

**What do citations verify?** They verify that returned excerpts match exact source fields/offsets and URLs. They do not prove the medical interpretation or entailment of generated prose.

**What is agentic about the workflow?** It coordinates a bounded set of typed interpretation, search, extraction, comparison/evaluation, verification and report steps. It is a deterministic finite-state equivalent to a small tool graph, not an unrestricted autonomous LLM agent.

**Is RAG operational without credentials?** Local MiniLM/FAISS/BM25 retrieval and verified source quotes run. The optional FLAN-T5-small generator also ran on CPU, but its real-source answer was incomplete; the draft is unverified and never changes rules. An Ollama adapter is available but actual Ollama inference was not performed.

**Can Docker run?** Configuration validation passes; an actual build was attempted and failed because the installed Docker Desktop engine is unavailable. Its backend reported an inaccessible inference socket rename. The local Python deployment is verified; no successful container build is claimed.

**Is the system suitable for actual patient selection?** No. Inputs are synthetic, reviews are local demo records, complex criteria remain unresolved, and expert/clinical validation is unavailable. A matching known-criteria result never proves full eligibility.

**What research should follow?** Independently double-annotated representative criteria, adjudicated disagreement, protocol-family-aware splits, fair equal-data multi-seed model comparisons, stronger temporal/scope parsing, calibrated abstention and properly labeled regional transfer evaluation. These are future work, not fabricated accomplishments.
