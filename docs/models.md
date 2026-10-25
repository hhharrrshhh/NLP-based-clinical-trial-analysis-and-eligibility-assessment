# Models and retrieval

The application uses real local CPU inference, separate from the deterministic eligibility parser. Run evidence is recorded in `reports/model_smoke.json` and `reports/retrieval_smoke.json`; absence of those successful reports is not evidence of a working model.

| Component | Model and pinned revision | Purpose |
|---|---|---|
| Biomedical NER | `d4data/biomedical-ner-all`, `015a4050c9ac99722e61c547aa9b4282bcbedc7f` | Biomedical entity spans |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2`, `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` | 384-dimensional source retrieval |
| Optional generated draft | `google/flan-t5-small`, `0fc9ddf78a1e988dac52e2dac162b0ede4fd74ab` | Executed experimental local generation; no entailment/eligibility claim |

All three pretrained model repositories declare Apache-2.0. The [biomedical model card](https://huggingface.co/d4data/biomedical-ner-all) describes a DistilBERT model trained on MACCROBAT clinical case reports. That domain differs from clinical-trial criteria. The pinned configuration actually contains 84 BIO/O labels, including `Disease_disorder`, `Medication`, `Age`, `Lab_value`, `Diagnostic_procedure`, and `Therapeutic_procedure`; claims about model-card entity counts are not used as evaluation truth. The [embedding model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) describes a short-text encoder and a default 256-wordpiece input limit.

Weights are cached under ignored `models/hf/` (override `TRIALOPS_MODEL_CACHE`). Loading uses pinned revisions, `trust_remote_code=False`, and safetensors. No Hugging Face API key is required for these public weights. `HF_HUB_OFFLINE=1` restricts loading to downloaded files. First use needs network access and several hundred MB of disk. The default is four CPU threads; set `TRIALOPS_TORCH_THREADS` if needed. Hardware and sampled process RSS are measured by the smoke script, not guessed model-memory claims.

NER processes every token using 512-token windows with 64-token overlap. At overlaps, the window with the greatest distance from its edge supplies each token prediction. BIO aggregation returns exact original character spans. It never silently truncates a long protocol. Requests over 100,000 characters are explicitly rejected. Entity scores are model softmax values, not calibrated probabilities of medical correctness. NER predictions never authorize executable eligibility rules.

Retrieval indexes exact substrings from study titles, descriptions, and eligibility text. Chunks retain study ID, source URL, source field, offsets, countries, and status. The 700-character windows overlap by 120 characters. Any chunk exceeding 220 wordpieces is represented by overlapping token windows whose normalized vectors are averaged and normalized again, ensuring no source text is silently lost to the embedding limit. Search uses BM25, normalized FAISS inner-product similarity, or reciprocal-rank fusion `sum(1/(60+rank))`. Region/status filters are applied before selecting the top results. Country never changes clinical thresholds. Rank scores are not calibrated evidence of clinical applicability.

Persistence contains `chunks.json`, `manifest.json`, `embeddings.npy`, and an interoperable `vectors.faiss`. Runtime verifies the corpus/model fingerprints and array checksum, disables NumPy pickle, validates dimensions and values, and rebuilds FAISS from arrays. It does not deserialize a supplied native FAISS file. A stale index is rebuilt. The checksum detects corruption, not malicious replacement of both manifest and data; use only locally generated artifacts.

If weights or FAISS fail, requests either raise (strict mode) or explicitly report `actual_mode: bm25_fallback` and the reason. Lexical results are never advertised as semantic. An empty or unrelated lexical query returns no evidence. Semantic retrieval by itself always ranks nearby vectors; the bounded answer workflow must additionally verify cited evidence and abstain when it does not answer the question.

Reproduce with `.venv\Scripts\python.exe scripts\model_smoke.py`, then `.venv\Scripts\python.exe scripts\build_index.py` after ingestion. The first script reports cold/warm latency, sampled process RSS, a synthetic example clearly labeled as such, a complete real study if present, and a long-input coverage check. The second verifies every returned chunk against its original source field.

NER and embeddings are not generative models. Optional local generation is now implemented and actually executed using pinned FLAN-T5-small (Apache-2.0, 77M parameters per its official model card). Generation is invoked only on request and remains an unverified draft: the real-source smoke question asking for an HbA1c requirement returned only "Glycated hemoglobin", an incomplete answer. Source excerpts remain the primary answer. Context selection/truncation, latency and a narrow numeric-token guard are recorded; none verifies entailment. `GENERATOR_BACKEND=none` disables drafts; `ollama` uses an optionally configured separate service. Actual Ollama inference was not performed. See `reports/generation_smoke.json` and `docs/generation.md`.

A real supervised frozen-encoder head adaptation has also been completed. Its 5,383-parameter BIO head is trained against CHIA labels, while all pretrained encoder parameters stay frozen. This is distinct from full transformer fine-tuning and from regional adaptation. See `docs/adaptation.md`, `reports/adaptation_benchmark.json`, and the ignored `models/adapted_chia_head/` artifact.

## Measured run and negative result

The completed CPU smoke run used 58 real studies and built 426 chunks in 16.554 seconds. All nine combinations of retrieval mode and example query returned source-verified results. Cached biomedical model load plus first inference took 7,556.969 ms; a subsequent 92-character example took 17.196 ms. Sampled peak process RSS during the whole smoke run was 685.527 MiB. An 8,516-character example traversed four windows and detected an entity in the final sentence. These are observed runs on this machine, not latency guarantees. Raw reports contain hardware, exact revisions, inputs, outputs, and timestamps.

`experiments/entity_benchmark.py` compares a dictionary learned only from 800 CHIA training studies with the frozen biomedical model on 40 documents from 20 held-out studies. CHIA has 1,000 studies; the other 180 held-out studies are unused. Deterministic SHA-256 ordering assigns studies to partitions, keeping inclusion and exclusion sections together. Five training documents with invalid source/annotation alignment were excluded and individually recorded; original CRLF characters are preserved. No test document was excluded. The dictionary has 7,262 terms learned from 15,556 in-scope training annotations.

The three-category scope maps CHIA Condition to model Disease_disorder, Drug to Medication, and Procedure to Diagnostic_procedure or Therapeutic_procedure. All gold spans in this scope are evaluated; discontinuous spans remain gold and cannot be matched by contiguous model spans. Exact category and exact offsets are required. The 40 test documents contain 328 gold entities.

| Model | Precision | Recall | Exact-span F1 | TP / FP / FN | Mean inference ms |
|---|---:|---:|---:|---|---:|
| Training dictionary | 0.3636 | 0.5122 | 0.4253 | 168 / 294 / 160 | 5.35 |
| Biomedical transformer | 0.1281 | 0.1250 | 0.1265 | 41 / 279 / 287 | 49.97 |

The pretrained model performs worse under this strict transfer evaluation. Differences in annotation ontology, span boundaries, clinical-report training domain, and trial-criteria language limit interpretation; the result does not establish general superiority of dictionaries. It directly argues against automatically treating biomedical NER output as validated trial eligibility. The evaluation is exploratory and uses a fixed subset rather than an official benchmark split. It is not full criterion extraction accuracy or regional adaptation. The original benchmark uses the untouched transformer; the separately executed head-adaptation experiment obtains F1 0.3212 on the identical test documents, between the original model and dictionary. The dictionary used more training data. Per-document outputs and comparison charts are retained.
