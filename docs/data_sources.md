# Data sources, provenance, and access

## ClinicalTrials.gov corpus

The shipped corpus was retrieved from the official [ClinicalTrials.gov API v2](https://clinicaltrials.gov/data-api/api) on **17 October 2026 at 08:38 UTC**. The saved run is `20261017T083822512361Z`. The official [OpenAPI specification](https://clinicaltrials.gov/api/oas/v2) was inspected before implementation and is retained in `data/raw/reference/clinicaltrials-v2-openapi.yaml`.

The executed command was:

```powershell
.venv\Scripts\python.exe -m scripts.ingest --per-region 30
```

Two queries used `query.cond=Type 2 Diabetes`, `query.locn=India` or `United States`, `sort=@relevance`, `format=json`, and `countTotal=true`. Initial page size was 20, followed by the next-page token and the remaining required count. There was no recruitment-status filter. After retrieval, each selected study was required to contain the query country in its actual listed locations; a keyword match alone was insufficient. The API reported 445 available India query matches and 3,766 United States query matches at retrieval time.

| Observed measure | Count |
|---|---:|
| Selections from India query | 30 |
| Selections from United States query | 30 |
| Distinct studies after NCT-ID deduplication | 58 |
| Studies with listed Indian locations | 32 |
| Studies with listed United States locations | 30 |
| Studies with locations in both countries | 4 |
| Location rows across all countries | 1,226 |
| Raw response pages | 4 |
| Missing eligibility descriptions | 0 |
| Overall status `RECRUITING` | 7 |
| Overall status `COMPLETED` | 39 |
| Overall status `TERMINATED` | 5 |
| Overall status `UNKNOWN` | 5 |
| Overall status `SUSPENDED` | 1 |
| Overall status `AVAILABLE` | 1 |

The distinction between 60 query selections, 58 distinct studies, and the country counts is intentional: only two studies were selected by both queries, but four distinct studies list both countries. A country is a site-location grouping, not nationality, ethnicity, medical suitability, or evidence for a population-level causal claim. Recruitment status belongs to a record; the presence of a listed site does not imply it is currently recruiting. API relevance ranking and this small convenience sample are not representative regional sampling. Regenerating the corpus may yield different records as registry contents and ranking change.

### Files and verification

- `data/raw/clinicaltrials/<run_id>/*.json` holds byte-preserved API response bodies. Each page has a `.provenance.json` sidecar recording UTC retrieval time, exact request URL and parameters, query region, relative raw path, and SHA-256.
- `data/raw/clinicaltrials/<run_id>/manifest.json` records every query, selected NCT ID, counts, skipped country mismatches, and completion/error status.
- `data/processed/studies.json` contains the complete normalized study objects consumed by the application. Each object carries its public study URL and a list of raw-page provenance references. Overlap does not erase either query reference.
- `studies.csv` contains normalized study metadata. List-valued fields use JSON array strings inside CSV cells; absent scalar values are blank.
- `eligibility_criteria.csv` preserves the original full eligibility text. Inclusion/exclusion segmentation is performed by the NLP component; this ingestion layer does not invent missing headings or requirements.
- `study_locations.csv` contains one row per listed location.
- `study_metadata.json` records counts, query definitions, and record-level provenance.

Missing optional API fields become `null`, an empty list, or an empty text field according to type. Missing/invalid NCT IDs or incompatible structural types stop ingestion. Requests have connect/read timeouts, four bounded attempts for transient failures, exponential delays, and HTTP 429 handling. HTTP 403 is not retried or bypassed. A failed run keeps raw evidence and its failure manifest; it does not replace the last complete normalized corpus. Repeated pagination tokens and excessive pages cause explicit errors.

The application reads `DATA_DIR/processed/studies.json`; `DATA_DIR` defaults to this repository's `data` directory. The store functions are `get_studies() -> list[dict]`, `get_study(study_id) -> dict | None`, and `get_metadata() -> dict`. Refreshing ClinicalTrials.gov preserves previously imported records whose registry is explicitly `CTRI`.

ClinicalTrials.gov is the public source, not a license invented by this project. Consult the registry's current [terms and conditions](https://clinicaltrials.gov/about-site/terms-conditions) before redistribution or a new use. The source is attributed on every record; this repository does not imply registry endorsement or independent verification of sponsor-submitted claims. The official site uses client-rendered documentation; the machine-readable official OpenAPI specification and successful live responses were used to verify the implementation.

## CTRI: compliant manual import

The official [CTRI public search](https://ctri.nic.in/Clinicaltrials/advancesearchmain.php) was inspected. It requires a security code. No supported public bulk API was identified during this inspection. This is an observed access limitation, not a claim that no authorized bulk mechanism could exist. No CAPTCHA, authentication, or access restriction was bypassed. **The shipped corpus contains zero native CTRI records.** India-site ClinicalTrials.gov records remain labeled `ClinicalTrials.gov`.

To add CTRI data, a researcher should use the registry's permitted public interface or obtain an authorized export, preserve the public record URL and original retrieval timestamp, and prepare CSV or JSON with these fields:

| Field | Requirement |
|---|---|
| `study_id` | Exact actual ID, in `CTRI/YYYY/MM/NNNNNN` form |
| `title` | Nonempty actual title |
| `eligibility_text` | Nonempty actual public eligibility text |
| `source_url` | The actual public record URL on `ctri.nic.in/Clinicaltrials/` |
| `retrieved_at` | ISO-8601 timestamp with timezone |
| `provenance_note` | How the public record was obtained and any transcription/normalization performed |
| `conditions`, `countries`, `phase` | JSON arrays of strings; JSON-array cells in CSV |
| `locations` | JSON array of objects with `facility`, `city`, `state`, `zip`, `country`, `status` where reported |
| `status`, `minimum_age`, `maximum_age`, `sex`, `description`, `last_update` | Optional source values; do not infer unavailable information |

JSON input must be a list of records. CSV must use headers and proper quoting for commas and multiline eligibility text. Do not turn the field descriptions above into fictional registry records. Import with:

```powershell
.venv\Scripts\python.exe -m scripts.import_ctri C:\path\to\actual_ctri_records.json
```

The importer validates required provenance, ID format, host, timestamp timezone, array formats, duplicate IDs, and file size. It preserves the original import bytes under a SHA-256 filename in `data/raw/ctri`, then regenerates all normalized tables with `registry=CTRI`. Validation cannot prove that manually transcribed content is authentic; review it against the public record. There is no automatic scraping or hidden network request. Unit tests use conspicuously synthetic fixtures only inside temporary test directories.

## Licensed annotation resources

### CHIA — downloaded for independent annotation evaluation

Kury, F., Butler, A., Yuan, C., et al. (2020), [Chia, a large annotated corpus of clinical trial eligibility criteria](https://doi.org/10.1038/s41597-020-00620-0), Scientific Data 7, 281. The actual [CHIA annotated dataset](https://doi.org/10.6084/m9.figshare.11855817) is licensed **CC BY 4.0**, verified from the official [Figshare article metadata](https://api.figshare.com/v2/articles/11855817). This is the annotation dataset's license, distinct from the separate CC0 catalog-metadata record.

The original `chia_with_scope.zip` (Figshare file 21728850, 2,512,094 bytes) was downloaded on 16 October 2026 and safely extracted into `data/external/chia`. Its publisher-reported MD5 `54b33164da88da88e47b2a009e150a82` matches the downloaded bytes; SHA-256 is `b51ec05ba42a3805daf9581dd22a305986f7c5ae3ca4dad36b70d37970fb69b2`. Original archive, Figshare metadata, and retrieval provenance are retained. The corpus contains 2,000 `.txt` and 2,000 `.ann` files covering inclusion and exclusion text for 1,000 NCT studies.

Brat annotations include entity labels, exact character offsets, discontinuous spans, and relations. **Decode original text bytes without newline translation:** `path.read_bytes().decode('utf-8')`. The original CRLF line endings count toward offsets. A full source integrity audit found 48,849 exact label-text matches and 21 mismatches among 48,870 text-bound annotation rows, including discontinuous spans. Evaluation must explicitly exclude/report mismatches or review repairs rather than silently use invalid offsets. These labels were created by the corpus authors; they are not model predictions. The corpus spans conditions beyond diabetes and is not an independently labeled India-versus-US evaluation set.

The original data and annotations remain unchanged. Any sampled evaluation files, label mapping, newline handling, and exclusions must be documented by the experiment. CC BY 4.0 requires attribution, a [license link](https://creativecommons.org/licenses/by/4.0/), and indication of changes. No training or adaptation result is implied by the corpus download.

### MACCROBAT — inspected, not imported

J. Harry Caufield's [official MACCROBAT dataset](https://figshare.com/articles/dataset/MACCROBAT2018/9764942) (version 2, 2020) states CC BY 4.0 and contains 200 published clinical case reports with manual brat annotations. It can support biomedical NER but is not a trial-eligibility ground truth set. It was not imported into the local patient workflow. The project uses synthetic profiles for evaluation; published case-report content is not represented as a synthetic cohort. Any model pretrained or fine-tuned on MACCROBAT must not be evaluated on overlapping examples as if independent.

## Executed ingestion validation

```powershell
.venv\Scripts\python.exe -m pytest tests/test_ingestion.py -q
```

Observed after implementation: **22 passed**. Coverage includes pagination, an empty page with a next token, repeated token rejection, overlap deduplication, missing optional fields, invalid schema, HTTP 403, timeout/server-error retries, complete network outage, CTRI provenance rejection, JSON and multiline CSV import, `DATA_DIR` store behavior, and raw-file SHA-256 plus original eligibility-text verification for every shipped study. Fixtures are separate from the real dataset.
