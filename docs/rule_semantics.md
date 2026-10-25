# Conservative rule semantics

This module compares explicitly synthetic observations with a deliberately small
grammar. It does not establish clinical eligibility or diagnose a condition.
`validated=true` means that the complete criterion matches a documented grammar,
not that a clinician has approved it. The application records a separate review
checkpoint. Real-world use always requires qualified human review.

## Processing and evidence

`backend.app.nlp.extract(text, study_id=None)` applies Unicode NFKC normalization
and expands comparison symbols while maintaining an index map to the original
text. Tokens retain negation, AND/OR, punctuation and original-order words.
Display-oriented sentence segmentation is separate from executable rule
boundaries. Whole paragraphs or bullets are grammar units; wrapped lines and
nested bullets stay attached. Every rule, unresolved criterion and entity has an
original `source_text`, zero-based `source_start`, exclusive `source_end`, and
`study_id`. Compound rule children cite their whole criterion, because extracting
a smaller substring could hide the logical context that gives them meaning.

Entities are descriptive matches, not validated facts or executable rules. No
lemmatization or stopword removal is applied to the grammar: deleting a negation
or changing a biomedical token would damage its semantics. Abbreviations are
mapped by an explicit lexicon. The retrieval module handles TF-IDF separately.

## Supported grammar

Numeric fields: `age`, `bmi`, `hba1c`, `systolic_bp`, `diastolic_bp`.
Canonical units are years, kg/m2, %, mmHg, mmHg respectively. Numeric operators
are `gt`, `gte`, `lt`, `lte`, `equals`, `between_inclusive`,
`between_exclusive`; the evaluator additionally accepts explicit `range` bounds
with `lower_inclusive`/`upper_inclusive`. Exact grammar examples include:

- `Age >= 18 years`, `BMI less than 30 kg/m2`, `HbA1c >= 6.5 %`.
- `Age between 18 and 65 years`, `BMI 20-30 kg/m2`.
- `Age between 18 and 65 years exclusive`, `18 <= age < 65 years`.
- `HbA1c >= 6 % and < 8 %`.
- `Age >= 18 years and (BMI < 30 kg/m2 or HbA1c < 8 %)`.
- `Participants must be between 18 and 65 years of age and must not have severe renal impairment.`

Bare ranges (`between`, `to`, a dash) follow the explicit inclusive convention
used by the requested prototype schema. `exclusive` excludes both endpoints.
Comparison operators express each endpoint exactly. This convention remains a
review item for source protocols; it is not a claim that all prose uses the same
meaning. Missing age/BMI units use a declared field convention and are marked
`unit_assumed=true`. HbA1c and blood pressure source criteria require explicit
units because they have incompatible common scales. Numeric profile values use
canonical units; `{value, unit}` observations request an explicit conversion.

Boolean conditions are exact phrases/abbreviations: Type 2 diabetes (T2DM/T2D),
Type 1 diabetes (T1DM/T1D), severe renal impairment, severe kidney disease,
pregnancy, and hypertension. They are distinct input fields: severe kidney
disease is not automatically equated with severe renal impairment. Bare
`diabetes` or `renal impairment` does not become a more specific diagnosis.
Negation is accepted in explicit forms such as `no T2DM`, `without hypertension`,
`must not have severe renal impairment`, or `not be pregnant`.

Groups have `kind="group"`, `logic="AND"|"OR"|"NOT"`, and `children`.
Leaves have `kind="condition"`, `field`, `operator`, `value` or `lower`/`upper`,
`unit`, `type`, validation metadata, and source evidence. Top-level rules are
conjunctive. An exclusion section wraps its entire criterion in NOT; it does not
reverse each atom independently. This preserves, for example, the difference
between exclusion for `A OR B` and exclusion for `A AND B`.

## Abstention boundaries

No successfully extracted fragment is executed when the remaining part of its
criterion is unsupported. Temporal conditions, history, duration, baseline or
screening qualifications, investigator discretion, exceptions, ambiguous medical
language, unknown units, and unparenthesized mixed AND/OR all require review.
`No T2DM or hypertension` abstains because the negation scope is ambiguous.
An unresolved list introduction such as “any of the following” blocks rule
execution throughout that section, avoiding an accidental AND interpretation of
its items. This intentionally lowers coverage. Unsupported terms still appear in
the verbatim unresolved list; entity matches may be shown independently.

This grammar does not implement temporal reasoning, dose/medication inference,
free-form diagnosis resolution, sex-specific thresholds, or general logical
satisfiability. It never derives thresholds from country, ethnicity or nationality.

## Measurements and conversion provenance

- 12 months = 1 year is the declared numeric-age convention. It is not a date of
  birth calculation and does not infer age at a future study visit.
- 1 conventional mmHg = 133.322387415 Pa; kPa is converted by multiplying by
  `1000 / 133.322387415`. The exact conventional definition is stated in the
  [Scripps manometry reference](https://scrippsco2.ucsd.edu/assets/publications/manometry_report_scripps_ref_gas_calibration_revision_of_2012_pub_2016.pdf).
  The [NIST conversion table](https://www.nist.gov/pml/special-publication-811/nist-guide-si-appendix-b-conversion-factors/nist-guide-si-appendix-b9)
  gives the rounded factor 133.3224 Pa.
- IFCC HbA1c (mmol/mol) is converted to NGSP (%) with
  `NGSP = 0.09148 * IFCC + 2.152`, as stated by the
  [NGSP master equation](https://ngsp.org/ifccngsp.asp). The source threshold is
  retained verbatim and the exact converted float is used, without rounding it
  into a new threshold. Sources were consulted during implementation.

These are unit conversions, not invented medical cutoffs. HbA1c results in
different unit systems may have reporting/assay precision limitations; the
prototype has no measurement-error model.

## Evaluation

`evaluate_profile(profile, rules, unresolved=None)` requires
`profile["is_synthetic"] is True`. Unknown and absent measurements stay UNKNOWN.
An absent diagnosis in a positive diagnoses list is not a negative observation;
use an explicit false boolean when synthetic absence is known.

| Operation | TRUE / UNKNOWN | FALSE / UNKNOWN | UNKNOWN / UNKNOWN |
|---|---|---|---|
| AND | UNKNOWN | FALSE | UNKNOWN |
| OR | TRUE | UNKNOWN | UNKNOWN |

NOT preserves UNKNOWN. An explicit false known constraint gives
`DOES_NOT_MATCH_KNOWN_CRITERIA`, even if unrelated criteria are unresolved.
Otherwise, missing information, an empty rule set, or unresolved criteria gives
`INSUFFICIENT_INFORMATION`. All true, resolved rules yield
`MATCHES_KNOWN_CRITERIA`, never “eligible”. Evidence, observed and normalized
values, explanations, and remaining unresolved criteria accompany every result.

Contradiction detection proves conflicts among unconditional conjunctive numeric
intervals and categorical equalities. It also handles NOT over simple conditions
and NOT over OR through De Morgan's law. A conflict forces
`INSUFFICIENT_INFORMATION` and protocol review. It does not claim to solve
arbitrary nested OR satisfiability. Malformed thresholds and unvalidated rules
return UNKNOWN rather than executing.

The legacy prototype's synthetic-only boundary, inclusive range behavior,
explicit false/unknown distinction, and numeric input names are preserved through
aliases. Its fictional regional thresholds are not imported into real-study
evaluation.

## Verification

Run `python -m pytest tests/test_nlp.py tests/test_eligibility.py -q` from the
repository root. These are developer-authored synthetic robustness cases, not
clinical validation or independent human-verified extraction ground truth.
