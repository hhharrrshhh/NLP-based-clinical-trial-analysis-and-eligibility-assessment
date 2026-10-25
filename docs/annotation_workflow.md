# Reference evaluation and annotation workflow

The saved experiment is runnable, but it is not a clinically validated extraction
system. `reports/research_metrics.json` records three distinct kinds of evidence:
developer semantic references, synthetic profile comparisons, and descriptive
analysis of real registry text. The regional data has no expert rule labels.

## What is labeled now

`data/annotations/developer_reference_cases.json` contains 75 explicitly authored
synthetic cases: 45 complete, unambiguous constraints representable in the declared
field/operator/unit/Boolean model and 30 unsupported or ambiguous cases. Expected
values are authored in `author_reference_cases.py`, which does not import or call
the parser. The evaluator reads the static JSON; it never copies predictions into
labels. Two lexical generalization challenges deliberately retain their expected
meaning even when the current parser abstains.

These labels are `developer_reference`, `expert_reviewed=false`, and
`blinded=false`. The author knew the parser contract and read its implementation
before authoring references. The references therefore test engineering fidelity;
they are not independent human gold or a sample from clinical practice. Existing
developer tests cover similar semantics. No clinical or external accuracy claim
is justified by either set.

The synthetic source ID groups all cases in a linguistic family. Within authored
executable and unsupported strata separately, families are sorted by
SHA256(`developer-reference-v1:` + family); the first floor(0.6K) families are
`train`, the next through floor(0.8K) are `dev`, and the remainder are `test`.
This assignment uses authored dispositions, never model predictions. A family
does not cross splits. The set is frozen in the JSON; adding families requires a
new reference-set version and a split review. `train` means illustrative cases
available for future development, `dev` means routine error review, and `test`
means reserved developer reference evaluation. No model is trained here. These
names do not make this a blinded external holdout; the test split has been run and
must be retired from final held-out claims if its errors guide a future change.

The current saved run has 44 train, 11 dev and 20 test references, including 12
expected-executable and eight unsupported test cases. On the reserved developer
test subset, complete rule fidelity is **10/12 (83.3%)**, with TP=10, FP=0, TN=8,
FN=2: FPR=0/8 and FNR=2/12. Across all splits the corresponding fidelity is
43/45 (95.6%), FPR=0/30 and FNR=2/45. Pooled results include development
references and must not be presented as held-out accuracy. Both missed cases are
test paraphrases: “Age must exceed 21 years” and “BMI is lower than 29 kg/m2”.
The expected labels remain unchanged and the parser was not modified to fit them.

`developer_reference_annotations.csv` is the same authored information in the
practical row schema. It repeats complete source spans for compound-rule atoms,
so a rule cannot silently lose an exception, section heading or negation scope.
The `entity` cell names the semantic field; these rows are not token-level NER
mention-boundary labels. No NER precision/recall is claimed from them.

## Metrics and denominators

Run from the repository root:

```powershell
.venv\Scripts\python.exe -m experiments.research_eval
```

The output includes per-case predictions, per-study CSV rows, JSON metrics and
two PNG figures under `reports/research/`. Recreate reference files only when
deliberately revising the reference set:

```powershell
.venv\Scripts\python.exe data/annotations/author_reference_cases.py
```

The binary positive class is a complete executable semantic representation. The
prediction is positive only when at least one rule exists and no unresolved text
or contradictions remain. TP/FP/TN/FN and FPR=FP/(FP+TN), FNR=FN/(FN+TP) include
their raw denominators. A separate counter records any emitted fragment on
unsupported cases, even when unresolved residue makes the binary prediction
negative. Abstention is a measured behavior, not an omitted case.

Field, operator, value, canonical unit (including an assumed-unit flag),
inclusion/exclusion type, negation scope, and logical shape each receive a
whole-case exact-match score over **all expected-executable cases**. Missing
rules, extra rules, incorrect atom order/tree paths, and abstentions count as
errors. These are case-level component accuracies, not per-token scores and not
conditional scores selected only from successful parses. Full rule match checks
the complete semantic tree, inclusive/exclusive endpoints, canonical values and
units, with absolute numeric tolerance 1e-6. IDs and source metadata are excluded
from semantic equality. Original-span integrity is checked separately; empty
documents have no emitted source items to violate the check.

The 18 synthetic profile references cover boundary values, missing observations,
AND/OR/NOT, explicit absent conditions, unresolved criteria, conversion, malformed
units and contradictions. Their status labels are also developer-authored; they
do not represent patient eligibility or outcomes.

Latency is warmed serial wall time over three passes through all 58 registry
documents, with mean, median, p95 and maximum. A separate memory pass records
Python allocation peak with `tracemalloc` and RSS sampled after parser calls.
RSS includes the interpreter and imported libraries and is not an OS peak or an
exclusive parser allocation. These are local CPU measurements, not a load test,
GPU benchmark or an end-to-end application response-time estimate. The JSON
records package versions, platform, input hashes and parser hash.

## Regional comparison without overlap leakage

The current convenience sample contains 58 unique CTgov studies: 28 India-only,
26 US-only and four shared studies. India appears in 32 records and the United
States in 30; the four shared records are counted once in the regional analysis.
“Only” means only one of these two target countries; other recruitment countries
may also appear. Recruitment country is not participant ethnicity.

Each study ID receives one stable split: integer SHA256(UTF-8 study ID) modulo 10
below eight is `train`, otherwise `test`. All text from that study stays in its
split. In the saved sample this yields 49 train and nine test records. All four
shared studies happen to be in train; comparisons requiring a shared test group
are unavailable, represented by JSON `null`. Exact normalized-document duplicate
groups are audited. Related protocols, copied paragraphs and near duplicates are
not clustered, so study-ID disjointness does not prove protocol independence.

TF-IDF vocabulary and IDF values are fitted on training eligibility text only.
The tokenizer applies NFKC, casefolding and alphanumeric-token filtering; all
stopwords are retained, including no/not/without/and/or. Neither stemming nor
lemmatization is performed in this experiment. The parser separately provides
offset-preserving tokens and display sentence spans; execution still requires
complete safe clause coverage. The code does not conflate sentence segmentation
with a safe executable rule boundary.

Empirical unigram Jensen–Shannon divergence is computed with base-2 logarithms,
without smoothing, over the union of each pair's observed vocabularies:
JSD(P,Q) = 0.5 KL(P||M) + 0.5 KL(Q||M), where M=(P+Q)/2. Both an all-text
descriptive comparison and a test-only comparison are saved. All-text JSD does
not train or select a model. The experiment also records vocabulary Jaccard,
train-fitted TF-IDF centroid cosine, top mean TF-IDF terms and unseen-token rates.
Differences may reflect protocol mix, study age, sample size or documentation
style. They do not establish learned domain adaptation or regional performance.

Coverage is parsed criteria divided by the parser's segmented criteria, not the
fraction of medically correct extractions. Segmentation itself is unvalidated on
regional text. Every group's `extraction_accuracy` remains `null` because there
are no independently adjudicated regional labels. Country-specific extraction
FPR/FNR, generalization improvement, clinical utility, and patient eligibility
accuracy cannot be calculated from this sample.

The saved coverage counts are 9/387 (2.33%) in India-only, 5/503 (0.99%) in
US-only, and 4/93 (4.30%) in shared studies: 18/983 (1.83%) overall. All 58 studies
require review. India-only versus US-only unigram JSD is 0.2026 across the full
sample and 0.3955 on the tiny test groups of three and six studies. The training
TF-IDF vocabulary has 2,190 terms. These values establish that the implementation
runs on real text while exposing its limited grammar coverage.

The saved local resource run covers 174 serial parser calls (58 studies, three
passes): median 1.69 ms and p95 7.78 ms, with a separate traced Python allocation
peak of 978,355 bytes and sampled RSS increase of 2,129,920 bytes. Measurements
vary with concurrent work and hardware; rerun JSON values take precedence over
these rounded snapshot values. All 18 authored synthetic profile status cases
match their expected statuses.

## Collecting independent annotations

Use `data/annotations/annotation_schema.json` as the CSV row contract. The supplied
`registry_annotation_queue.csv` contains actual full registry source documents,
source URLs and frozen study splits, with **all semantic label cells blank**.
Its `label_origin=unannotated` and `reviewer=unassigned` explicitly distinguish it
from the synthetic references. Blank means missing, never an unsupported/negative
gold label. The queue is a starting point, not completed annotation.

Regenerate the unlabeled queue from the saved registry snapshot with
`.venv\Scripts\python.exe data/annotations/prepare_registry_queue.py`.

1. Freeze the exact registry snapshot, retrieval time and source hash. Assign
   studies to train/dev/test before extracting annotation units; keep an entire
   study and, where known, protocol family together. Reserve a prospective test
   set before developing rules on new annotations. Shared-country studies belong
   to their own group and one split.
2. Ask two qualified reviewers to independently read the complete source and
   mark criterion evidence spans with zero-based Unicode code-point offsets and
   an exclusive end. Verify `exact_span == text[start:end]`. Preserve headings,
   nested lists, exceptions, temporal wording, negatives and connective scope in
   the evidence, even when an individual atom is shorter. Do not expose parser
   suggestions during an independent first pass.
3. For each atom record normalized field/entity, category, comparator, numeric
   value or range bounds, original and canonical unit interpretation, lexical
   negation, inclusion/exclusion type, complete AND/OR/NOT logical signature and
   whether the **whole criterion** is representable. Keep the source unit visible
   in the exact span, and document any conversion or implicit convention in the
   rationale. Label unsupported portions explicitly; never invent absent units,
   disease subtype, temporal reference point or an AND/OR interpretation.
4. Keep original reviewer files and reviewer IDs. Compare span, field, operator,
   threshold, unit, type, negation and logic agreement separately; disagreement
   about unsupported meaning is substantive. A third reviewer adjudicates
   disagreements against the complete protocol. Record that reviewer's decision
   and rationale, then change `label_origin` to `expert_adjudicated` only for
   rows actually reviewed. The current repository has no such rows.
5. Validate IDs, offsets, JSON signatures, units, missing-value handling and
   split isolation before scoring. Compute extraction precision/recall and full
   rule fidelity against adjudicated labels with explicit denominators. Evaluate
   synthetic profile comparison separately. Report group sizes and uncertainty;
   small regional samples cannot support broad national or clinical claims.
