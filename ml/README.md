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
