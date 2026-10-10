# Green Customer Insights Platform - ML core

This pipeline implements the four mandatory Lloyds opportunities and emits one validated JSON object per
`customer_id + product_code` pair using Final JSON Contract `1.0.0`.

For a detailed explanation of the architecture, models, rules, impact calculations, output schema and team workflow,
read the [ML technical walkthrough](../output/pdf/green_insights_ml_technical_walkthrough.pdf).

## How it works

```text
Synthetic source tables
        -> transaction categorisation
        -> Customer 360 features
        -> product propensity + confidence + reason codes
        -> eligibility rules
        -> deterministic sustainability impact
        -> recommendation decision
        -> verified explanation + audit metadata
        -> JSON Schema validation
```

The responsibilities remain deliberately separate:

- ML predicts product take-up propensity and categorises transactions.
- Eligibility rules decide whether an opportunity may be shown.
- The carbon engine calculates estimated impact from documented formulas and factors.
- The explanation layer can only explain approved structured fields.

A high propensity cannot override a failed rule. The validated test output includes a high-propensity EV case that
is still `INELIGIBLE`, `DO_NOT_RECOMMEND`, and `customer_visible=false`.

## Run

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r ml/requirements.txt
.venv/bin/python ml/run_pipeline.py
```

The default run creates 5,000 synthetic customers and 20,000 opportunity records. For a quick smoke test:

```bash
.venv/bin/python ml/run_pipeline.py --customers 1000
```

Main outputs:

- `ml/outputs/opportunities_all.jsonl`: canonical records for all customer-product pairs.
- `ml/outputs/test_predictions.jsonl`: untouched test-customer records.
- `ml/outputs/recommendations_summary.csv`: dashboard-friendly flat summary.
- `ml/outputs/evaluation_report.json`: transaction and propensity metrics, baselines, confidence intervals,
  selected LightGBM/logistic-regression blend, and thresholds.
- `ml/contracts/opportunity_v1.schema.json`: machine-readable integration contract.

Large generated JSONL and CSV artifacts are intentionally excluded from Git and can be reproduced with the run
command. The trained model files, compact evaluation report, feature weights, CV results, schema, and tests are
stored in the shared branch.

## Validate the safety rules

```bash
PYTHONPATH=ml .venv/bin/python -m unittest discover -s ml/tests -v
```

The current tests cover:

- an existing EV owner who must be blocked;
- missing mileage that must become `MANUAL_REVIEW`;
- a non-homeowner who must be blocked for Solar Finance.

## Team branch

```bash
git fetch origin
git switch feature/ml-json-contract-v1
```

GitHub branch: <https://github.com/dev-rjt/FineShyt/tree/feature/ml-json-contract-v1>

## Run on the team's canonical dataset

The commands above regenerate the ML module's original standalone synthetic dataset. For the team's actual
`data/` pipeline, use this command instead:

```bash
.venv/bin/python ml/run_project_dataset.py
```

It reads:

- `data/processed/customer_360.csv`;
- `data/processed/product_takeup_labels.csv`;
- `data/processed/transaction_category_labels.csv`;
- the exact customer splits under `data/splits/`;
- `data/reference/emission_factors.csv` and `green_products.csv`.

It first requires `data/reports/validation_report.json` to have `overall_status: PASS`. It then trains the
transaction classifier and four propensity models, creates 20,000 customer-product records, and writes them to
`ml/outputs/project_dataset/`.

For a faster propensity-only retrain after the transaction model already exists:

```bash
.venv/bin/python ml/run_project_dataset.py --skip-transaction-model
```

Project-specific trained artifacts are:

- `ml/models/project_txn_classifier.joblib`;
- `ml/models/project_propensity_models.joblib`;
- `ml/outputs/project_evaluation_report.json`.

### Score one customer without retraining

Training is an offline operation. The final app must load the saved model and run inference; it must not retrain
when a user opens a screen.

```bash
.venv/bin/python ml/predict_project_dataset.py \
  --customer-id C00001 \
  --output ml/outputs/project_dataset/C00001.json
```

The output contains exactly four objects: EV Finance, Green Home Loan, Solar Finance, and Paperless Banking.

## How the final app uses this

1. The data pipeline periodically rebuilds Customer 360 from transactions, products, vehicles, energy, and digital use.
2. An offline training job updates the saved models only when approved training data or model code changes.
3. When the dashboard requests a customer, the backend calls `predict_project_dataset.predict(data_root, customer_id)`.
4. The model supplies propensity, confidence, and reason evidence for all four products.
5. Eligibility rules can block the opportunity or request missing information even when propensity is high.
6. The deterministic impact engine calculates the estimate using the versioned 2026 factor catalogue.
7. The backend returns the validated JSON object to the frontend.
8. The customer screen shows only records with `customer_visible=true`; the manager and audit screens can also show
   blocked and manual-review records with their decision codes.

The frontend should not recalculate scores, eligibility, or impact. It should display the structured backend result.

Real data later:

```bash
.venv/bin/python ml/adapt_to_real.py real_customer_360.csv EV_FINANCE takeup_EV_FINANCE
```

## Role split (as the brief requires)
ML (validation-selected LightGBM/logistic blend) -> propensity + confidence | `rules.py` -> eligibility gate |
`carbon_engine.py` -> deterministic impact | deterministic verified fallback -> explanation. An LLM may later replace
only the explanation writer; it must never change prediction, eligibility, impact, or recommendation fields.

## Synthetic label generator: coefficients ("weights") on standardised features (z) - data_generation.make_takeup
logit = intercept + sum(w*feature) + N(0, 0.9) unobserved noise ; take-up ~ Bernoulli(sigmoid(logit)) ; only for rule-candidates
EV_FINANCE   (-4.0): mileage +0.90z | fuel spend +0.75z | sustainability pref +0.90z | existing vehicle loan +0.60 | vehicle age>7y +0.45 | income +0.35z | urban +0.50 | home owner +0.30 | age -0.02/yr
GREEN_HOME_LOAN (-4.0): heating kWh +0.85z | sustainability +0.90z | home-improvement spend +0.55z | mortgage +0.70 | income +0.30z | age 28-62 +0.30
SOLAR_FINANCE(-4.1): electricity kWh +1.00z | sustainability +0.95z | income +0.50z | home-improvement spend +0.35z | rural +0.40 | ISA holder +0.35
PAPERLESS_BANKING (-1.9): paper share +2.2*(share-0.4) | digital tx +1.10z | branch visits -0.90z | digital usage +0.50z | sustainability +0.30z | age -0.02/yr
Candidate (eligibility) rules: see rules.py. Outcome window: 6 months after cutoff 2025-12-31.

## Important limitations

- All customer and outcome data is synthetic. Reported metrics demonstrate the pipeline, not real-world performance.
- Emissions factors in `ml/data/emissions_factors.csv` are documented prototype values and must be replaced with
  the institution-approved, versioned factor set before production use.
- Eligibility rules are illustrative and must be replaced by the institution's authorised criteria.
- No real personal or confidential banking data is included.
- Product take-up uses a six-month outcome window after the 2025-12-31 cutoff.
