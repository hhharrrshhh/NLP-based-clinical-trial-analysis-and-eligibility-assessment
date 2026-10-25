# Supplied prototype audit

The supplied DOCX is background/reference material. The separately pasted master prompt supplies the user's requirements. All five files in the ZIP were inspected. The original files remain in `legacy/TrialOps_Adaptive_Demo` unchanged.

Executed `python -X utf8 legacy/TrialOps_Adaptive_Demo/trialops_adaptive_demo.py --test`: all four existing sanity checks passed. Re-executed the seeded generator into `reports/legacy_reproduction`: 30 synthetic profiles, 60 evaluations; fictional India protocol 7 pass/20 fail/3 review, fictional US protocol 12 pass/15 fail/3 review. These are software outputs, not accuracy or population statistics.

Reusable semantics: deterministic comparisons, explicit missing values, failure taking precedence over unknown for a conjunction, traceable per-rule explanations, seeded synthetic data. Limitations: only three inclusive ranges and two booleans; no text ingestion, NLP, source provenance, clinical validation, domain adaptation, trained model, retrieval, API, UI, or Docker. Existing tests are narrow sanity checks, not a clinical validation study.

The new application preserves the useful semantics, retains the old demo separately, adds actual source records and model inference, and refuses to infer country-specific thresholds. The synthetic cohort's original geographic label is not used as a clinical attribute.
