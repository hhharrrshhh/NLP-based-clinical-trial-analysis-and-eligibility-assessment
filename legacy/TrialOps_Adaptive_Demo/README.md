# TrialOps-Adaptive AI — Safe Educational Simulator

This minimal project generates **30 fictional patient profiles** tagged as a synthetic India demo cohort and assesses each against **two entirely fictional study protocols** (one located in India, one in the US). It is not real-world medical data, an NLP model, a learned country-adaptive ML model, or clinical decision support.

## Run (Python 3.9+; no extra packages)

```bash
python trialops_adaptive_demo.py --test
python trialops_adaptive_demo.py
```

Produces:
- `synthetic_india_profiles.csv` — 30 fictional profiles, some with intentionally missing data.
- `fictional_trial_comparison.csv` — 60 hypothetical protocol-specific assessments, including traceable reasons and `needs_review` where appropriate.

## How this fits the intended NLP project

1. **Data generator and rule-engine baseline (implemented here)** — synthetic profiles and verified logic.
2. **Actual trial source ingestion (not implemented)** — collect selected public trial *registrations* from CTRI and ClinicalTrials.gov; respect data access/terms.
3. **Biomedical NLP (not implemented)** — hand-annotate a test set of inclusion/exclusion criteria and benchmark extraction of attributes, units, comparators, negation and ranges.
4. **Rule compilation and validation (not implemented)** — clinician-reviewed structured representation of real trial-specific criteria, with a review queue for ambiguity.
5. **Evaluation and deployment (not implemented)** — precision/recall/F1 for extraction; error analysis; coverage/abstention; API/Docker/UI. Results should explicitly be limited to hypothetical screening, not actual eligibility.
6. **True domain adaptation (future research)** — only claim it after training with permissioned, representative, labeled region-specific data, strong held-out validation, and assessment of subgroup performance; a geographic dropdown is not domain adaptation.

## Data sources for future work

- India trial registrations: https://ctri.nic.in/ (includes registered *trial* eligibility criteria, not patient biometric records).
- Global trial registrations and API: https://clinicaltrials.gov/ and https://clinicaltrials.gov/data-api/api
- EHR data (requires credentialed access; do not assume Indian subgroup is identifiable): https://physionet.org/content/mimiciv/3.1/

**Safety and validity:** Synthetic data must never be passed off as Indian patient observational data. Protocol thresholds in `fictional_trial_protocols.json` are invented exclusively to test software behavior and must not be represented as official ICMR/FDA BMI or HbA1c standards, health-risk thresholds, or actual trial selection criteria. Do not use results to screen real patients, diagnose disease, or make medical decisions. Country-of-study alone does not determine BMI or HbA1c cutoffs, nor does a trial-level rule engine prove that geographic domain adaptation occurred. Real protocols can contain far more criteria, exceptions and clinician judgment requirements.
