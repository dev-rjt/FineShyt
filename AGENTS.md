# Rules for AI agents working in this repo (Megathon X PS1: Glass-Box Green Insights)

Project: an AI platform that finds green financial product opportunities from synthetic customer data, estimates sustainability impact, explains each recommendation, and serves it through a FastAPI backend and a Streamlit dashboard.
Stack: Python, PostgreSQL, pandas, scikit-learn, XGBoost or LightGBM, SHAP, FastAPI, Streamlit.

## The core rule (never break it)
- ML models make predictions (propensity, confidence, transaction category).
- The rules-based carbon engine computes all impact figures from documented formulas, emission factors and assumptions. No ML and no LLM in the carbon engine.
- The LLM only explains structured outputs. It never predicts, calculates impact, or decides eligibility.
- Propensity is not eligibility. Never write that a customer is "eligible", "approved", "pre-approved", "qualifies" or has a "guaranteed" outcome. Use "subject to eligibility checks".
- Impact figures are estimates and are always ranges with a stated method.
- CO2e, energy, paper and digital adoption are reported separately. Never add them together.

## Working rules
1. `docs/API_CONTRACT.md` is the source of truth for every endpoint and field. Match it exactly (paths, `snake_case` names, enums, status codes, error shape).
2. `db/schema.sql` is the source of truth for tables. Do not create tables from code.
3. Edit only the folder you were asked to work in (`src/data`, `src/ml`, `src/engine`, `src/llm`, `src/api`, `src/common`, `app`), plus that role's own `tests/` subfolder and its own file in `docs/`. If you need a change elsewhere, stop and say so.
4. If the contract or schema needs to change, stop and say so. Do not change them silently. Once the team agrees, add a line to the change log in `docs/API_CONTRACT.md`.
5. Never hardcode emission factors or assumptions. Read them from the `emission_factors` and `model_assumptions` tables. Never invent a factor value; if it is missing, return `INSUFFICIENT_DATA`.
6. Never use `gen_hidden_factors` as a model feature. Use only data dated on or before the cutoff date. Split by customer, and hold out unseen merchants when evaluating the categoriser.
7. Reason codes come only from the fixed vocabulary in `reason_codes`. No free-text reasons.
8. Fixed random seeds everywhere. Results must be reproducible with `make run-all`.
9. Keep changes small and runnable. After each change, say how to test it (a `curl` command, a test, or a page to open).
10. Do not add large new dependencies without asking. Never put secrets in code or prompts; use `.env`.
11. All data is synthetic or lawfully public. Never add real personal or banking data. The LLM receives only the structured payload (no raw transactions, no postcodes, no names).
12. Call the LLM only through `src/llm/client.py`. Tests mock it, so they run with no network and no API key. The template fallback must always work.
13. `SUPPRESSED` opportunities never reach customer-facing endpoints or the LLM. They appear only in the audit view.
14. `USE_STUBS=true` must keep working so the dashboard can always be developed and demoed against stable data.
