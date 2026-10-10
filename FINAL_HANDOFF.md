# Final Hackathon Handoff

## Start the complete product

```bash
cd product_app
chmod +x run_demo.sh
./run_demo.sh
```

The first run creates a local demo configuration and installs dependencies. Open
<http://127.0.0.1:8502>. The launcher starts both the FastAPI service and the
Streamlit product and stops the API when the UI exits.

| Experience | User ID | Password |
|---|---|---|
| Bank workspace | `bank_manager` | `GreenBank@2026` |
| Customer portal | `C12558` | `GreenCustomer@2026` |

The credentials protect synthetic localhost demo data only. Replace them before
deploying anywhere shared.

## What happens after sign-in

1. FastAPI verifies the credentials and creates a signed, role-scoped session.
2. FastAPI reads the normalised SQLite customer, product, vehicle, energy,
   digital and transaction tables; these are joined into the Customer 360 feature row.
3. The transaction classifier assigns exactly one sustainability category to
   each transaction; the feature pipeline aggregates those categories.
4. Four trained propensity ensembles score EV Finance, Green Home Loan, Solar
   Finance and Paperless Banking. They output interest propensity, confidence
   and fixed evidence codes; they do not decide financial eligibility.
5. Product rules run independently and can suppress a high-scoring opportunity.
   The rules never get overridden by the model, customer memory or wording layer.
6. The deterministic carbon engine calculates the modelled 12-month impact from
   documented activity inputs, formulas, versioned factors and table-driven
   assumptions. Every result has a low/central/high range. Missing inputs return
   insufficient data instead of a guessed figure.
7. The explanation layer receives only structured approved facts. Optional model
   wording is verified; any invented number or provider failure falls back to
   reviewed deterministic text.
8. The API applies role authorisation. A customer can retrieve only their own
   profile and non-suppressed opportunities; the bank role can access portfolio
   aggregates, full four-product decision audits and authorised drill-down.
9. The customer portal presents relevance, evidence, estimated annual impact,
   methodology and a clear action. The bank workspace adds portfolio opportunity,
   segmentation, trends, impact planning, model governance, a live database
   catalogue and risk controls.

## Problem-statement check

All seven functional requirements are implemented. Required products GP01–GP04
are covered. Emissions, energy, paper and digital-adoption measures are reported
separately. The submitted repository includes source, preprocessing, trained
models, inference, explanation implementation, architecture, evaluation,
Responsible AI evidence and test predictions.

The honest boundary is equally important: this is a reproducible synthetic-data
prototype, not a production eligibility service. Propensity is not eligibility;
impact is estimated rather than measured; real deployment requires authorised
bank rules, current approved factors, production identity/MFA, security and
privacy review, accessibility testing and ongoing model-risk monitoring.

## Rebuild and verify

```bash
make verify
```

This rebuilds the range estimates and normalised database, then runs the final
product, dataset, ML contract, Responsible AI, rules engine, reference-engine
and grounded-LLM suites. The final audit pass executes 223 tests.
