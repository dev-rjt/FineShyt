# Submission Gap Audit

This audit compares the running `product_app` against the supplied problem
statement, team guide, frozen JSON contract and repository rules. It records
what was found during the final integration pass and the implemented fix.

| Area | Finding | Resolution | Evidence |
|---|---|---|---|
| Customer safety | The final API returned all four scored products, including rule-suppressed products, to customer sessions. | The customer endpoint now excludes `SUPPRESSED`; a bank-only audit endpoint retains all four outcomes and their gate reasons. | `product_app/api.py`, API integration tests |
| Contract shape | The final endpoint returned the internal flat batch row rather than the frozen nested Opportunity object. | Added a canonical adapter and validated audit records against `contracts/opportunity_v1.schema.json`. | `product_app/api_service.py`, `product_app/tests/test_api.py` |
| Product codes | Runtime codes `GREEN_HOME` and `PAPERLESS` did not match the contract. | API responses use `GREEN_HOME_LOAN` and `PAPERLESS_BANKING`; internal codes remain isolated behind the adapter. | `EXTERNAL_PRODUCT_CODE` mapping |
| Impact uncertainty | The UI showed point estimates for most calculations. | Every product now returns ordered low, central and high 12-month ranges; the UI shows the range. | `product_app/carbon_engine.py`, carbon-engine tests |
| Provenance | Emission factors lacked stable IDs, source year and version. | Added factor IDs, source years and versions; the method panels show factor provenance. | `product_app/data/emissions_factors.csv` |
| Assumptions | Scenario assumptions were hard-coded inside Python. | Assumptions are versioned reference data, loaded into the database, and visible in the planner. | `model_assumptions.csv`, `model_assumptions` table |
| Solar edge case | A small annual-use scenario could imply more displaced electricity than the customer consumed. | Generation is capped at annual use and regression-tested. | `test_solar_scenario_cannot_displace_more_than_annual_use` |
| Database | The earlier final app depended on flat files and did not expose an inspectable schema. | Added a normalised SQLite database with foreign keys, indexes, view, reproducible builder and an in-app data catalogue. | `db/schema.sql`, `db/build_demo_db.py` |
| Containers | Docker Compose still launched an obsolete stub API and attempted to feed SQLite SQL into PostgreSQL. | Docker now launches the actual FastAPI + Streamlit product and its SQLite build path. | `Dockerfile`, `docker-compose.yml` |
| Reproducibility | There was no single verification command. | Added `make verify` to rebuild impacts/database and run all test groups. | `Makefile` |

## Deliberate prototype boundaries

- Data is synthetic. No claim is made that the propensity models are calibrated
  for real Lloyds customers.
- Product gates are demonstrator rules, not financial eligibility or credit
  decisions.
- Impact is a deterministic planning estimate, not measured reduction or PCAF
  financed emissions.
- Approximate factors and assumptions must be replaced with the institution's
  currently approved sources before production use.
- Demo credentials and signed local sessions demonstrate role separation; a
  production deployment needs the bank identity provider, MFA, secrets
  management, rate limits, security testing and formal privacy approval.
