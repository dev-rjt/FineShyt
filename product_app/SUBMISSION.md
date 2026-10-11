# Verdant - Green Customer Insights Platform

This folder is the final Megathon submission. It consolidates the useful work
from the dataset, ML contract, backend, product-engine, and Responsible AI
branches into one runnable full-stack prototype.

## One-command demo

```bash
chmod +x run_demo.sh
./run_demo.sh
```

Open <http://127.0.0.1:8502>. FastAPI documentation is available at
<http://127.0.0.1:8000/docs> while the demo is running.

On first run, `run_demo.sh` generates unique local demo passwords, stores only
salted scrypt verifiers, and prints the passwords to the terminal. Do not reuse
local demo credentials in a hosted deployment.

`run_demo.sh` starts both services, waits for the API health check, and shuts
the API down when Streamlit stops. The checked-in model and scored artifacts
make startup fast. To reproduce them from source, run:

```bash
.venv/bin/python run_pipeline.py
```

## What is integrated

| Layer | Implementation |
|---|---|
| Data | Seeded 5,000-customer synthetic banking, transaction, vehicle, energy and digital data |
| Feature store | One Customer 360 row per customer; customer-level train/validation/test split |
| Transaction ML | TF-IDF classifier with a documented mutually exclusive category set and rules baseline |
| Propensity ML | Four calibrated, five-seed LightGBM ensembles with confidence and reason codes |
| Product rules | Deterministic gates override propensity and suppress conflicts |
| Impact engine | Deterministic baseline-vs-scenario calculations from the factor catalogue |
| Explanation | Narrow structured payload, grounded-number verifier, safe template fallback, optional LLM |
| Backend | FastAPI with signed sessions and customer/bank authorization |
| Frontend | Streamlit customer portal and multi-page bank workspace |
| Governance | Evidence timestamps, limitations, model health, subgroup monitoring, scenario controls |

## Problem-statement coverage

| Requirement | Delivered evidence |
|---|---|
| FR1 Customer 360 | `features.py` combines customer, product, vehicle, energy, digital and categorised transaction signals into one row per customer. |
| FR2 Transaction categorisation | `transaction_model.py` assigns one mutually exclusive category and reports model-vs-rules evaluation. |
| FR3 Opportunity detection | Four saved propensity ensembles emit propensity, confidence and reason codes for GP01–GP04. |
| FR4 Sustainability impact | `carbon_engine.py` owns deterministic baseline-vs-scenario estimates with factors, methods, assumptions and a 12-month horizon. |
| FR5 Customer insight | `insight_layer.py` explains approved structured facts, verifies generated numbers and safely falls back to deterministic wording. |
| FR6 Business insights | The bank workspace shows portfolio KPIs, products, regions, segments, trends, conversions and separate CO₂e/energy/paper/digital metrics. |
| FR7 Explainability | Each opportunity carries evidence, confidence, timestamp and rule status; ruled-out products are suppressed. |
| Required UX | Separate signed-in customer and bank experiences, customer actions, drill-down and a live scenario planner. |
| Evaluation | Held-out results, simple baselines, uncertainty, feature importance, subgroup monitoring, scenario tests and limitations are included. |

## Main evidence

- `models/`: trained transaction and propensity models.
- `outputs/evaluation_report.json`: held-out metrics and baseline comparisons.
- `outputs/test_predictions.csv`: untouched test-customer predictions.
- `data/emissions_factors.csv`: versioned factor values, units and sources.
- `carbon_engine.py`: deterministic sustainability calculations.
- `rules.py`: product-rule gates.
- `insight_layer.py`: constrained explanation payload and verifier.
- `api.py`: authentication, authorization and protected API routes.
- `api_service.py`: live integration of model, rules and engine.
- `app.py`: customer and bank experiences.

## Verification

```bash
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v
```

The final verification also passed the source branch suites: five ML safety
tests, six dataset integrity tests, and 105 engine, contract, privacy, leakage,
scenario, schema and Responsible AI tests.

## Important boundary

This is a synthetic-data hackathon prototype. Propensity is not eligibility,
all impact figures are estimates, and the included rule gates are illustrative.
Production use requires the bank's identity provider, authorised financial
eligibility process, current approved emission factors, security review, model
risk governance, accessibility review, monitoring, and human oversight.
