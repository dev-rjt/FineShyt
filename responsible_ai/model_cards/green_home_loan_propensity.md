# GREEN_HOME_LOAN propensity model card template

Status: TEMPLATE ONLY. No trained model or metrics are supplied by this package.

| Item | Owner must complete |
|---|---|
| Model version | `<ML_OWNER_VERSION>` |
| Training run/seed | `<ML_OWNER_SEED>`; record separately from anonymisation seed 2026 |
| Algorithm/hyperparameters | `<ML_OWNER_DETAILS>` |
| Training input | `data/doctored/processed/customer_360.csv`; feature subset from `features_loader.py` |
| Label table | `data/doctored/processed/product_takeup_labels.csv`, filtered to GREEN_HOME_LOAN |
| Target | Existing `take_up`; post-cutoff outcome window from `outcome_window_days` |
| Cutoff | Existing `data_cutoff_date` and label `cutoff_date`; dataset 2026-06-30 |
| Label provenance | Existing `label_method`; synthetic outcomes are not observed bank demand |
| Split | Existing train/validation/test customer CSVs; disjoint customers, no fitted preprocessing on held-out data |
| Training rows/customers | `<ML_OWNER_COUNTS>` |
| AUROC / average precision | `<NOT_MEASURED>` |
| Calibration / Brier score | `<NOT_MEASURED>` |
| Threshold / precision / recall | `<NOT_MEASURED>` with threshold rationale; no eligibility threshold inferred |
| Band diagnostics | `<NOT_MEASURED>` from `bias_audit.py`; suppressed groups excluded |
| Approved feature manifest | `<EXACT_SUBSET_AND_VERSION>`; never IDs, age, provenance or labels; income banned by default |
| External-source attribution | UCI Online Retail II / UK Power Networks where seeded; preserve source licence notices |
| Reviewer/date | `<HUMAN_REVIEWER_AND_DATE>` |

Limitations: synthetic propensity is not real take-up validation; proxy bias remains
possible after removing age/income. Confidence is not the probability of take-up.
Eligibility rules remain authoritative. Correlation checks do not prove no leakage.
Impact estimates come from the carbon engine, never this model. Missing inputs must
be handled and documented by the ML owner; this package does not impute them.

Evidence: `leakage_audit.py`, `features_loader.py`, `contract_checks.py`,
`bias_audit.py`, and generated reports in `data/reports/rai/`.
