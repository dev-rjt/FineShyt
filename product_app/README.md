# Green Customer Insights Platform - ML core (synthetic 5,000 customers)

Run: `./run_demo.sh` (uses the included trained models and scored synthetic data)

Open <http://127.0.0.1:8502>. The app starts at a role-based sign-in screen.
The launcher also starts the authenticated FastAPI backend on
<http://127.0.0.1:8000>; interactive API documentation is at `/docs`.

On first run, the launcher creates a private local `.env` with salted scrypt
password verifiers and a random session-signing secret, then prints the unique
passwords once. Existing local plaintext password entries are migrated on the
next launch. Hosted deployments must provide their own password hashes and
session secret. Generate each hash with
`.venv/bin/python init_local_env.py --hash-password` and set it as the matching
`*_PASSWORD_HASH` environment variable.

For hosting, the repository root contains a Render Blueprint. Its
`start_hosted.sh` launcher runs the API internally and exposes only Streamlit on
the platform-assigned port. See the root `README.md` for deployment steps.

The customer account is bound to one synthetic customer and can only open that
customer's recommendations. The bank account opens the portfolio dashboard,
customer drill-down, impact lab, model evaluation, and trust centre. This is a
hackathon authentication boundary; production must use an identity provider,
MFA, server-side authorisation, secret management, and audit logging.

See `SUBMISSION.md` for the judging checklist, `ARCHITECTURE.md` for the complete
flow, and `RESPONSIBLE_AI.md` for the governance note.
Real data later:  python adapt_to_real.py real_customer_360.csv EV_FINANCE takeup_EV_FINANCE

## Role split (as the brief requires)
ML (LightGBM) -> propensity + confidence | rules.py -> eligibility gate | carbon_engine.py -> CO2e (deterministic) | LLM (next step) -> explains structured JSON only.

## Synthetic label generator: coefficients ("weights") on standardised features (z) - data_generation.make_takeup
logit = intercept + sum(w*feature) + N(0, 0.9) unobserved noise ; take-up ~ Bernoulli(sigmoid(logit)) ; only for rule-candidates
EV_FINANCE   (-4.0): mileage +0.90z | fuel spend +0.75z | sustainability pref +0.90z | existing vehicle loan +0.60 | vehicle age>7y +0.45 | income +0.35z | urban +0.50 | home owner +0.30 | age -0.02/yr
GREEN_HOME   (-4.0): heating kWh +0.85z | sustainability +0.90z | home-improvement spend +0.55z | mortgage +0.70 | income +0.30z | age 28-62 +0.30
SOLAR_FINANCE(-4.1): electricity kWh +1.00z | sustainability +0.95z | income +0.50z | home-improvement spend +0.35z | rural +0.40 | ISA holder +0.35
PAPERLESS    (-1.9): paper share +2.2*(share-0.4) | digital tx +1.10z | branch visits -0.90z | digital usage +0.50z | sustainability +0.30z | age -0.02/yr
Candidate (eligibility) rules: see rules.py. Outcome window: 6 months after cutoff 2025-12-31.

## Emissions factors: data/emissions_factors.csv - approximate UK DESNZ-style values, MUST be verified against the latest published set before any real use.

## Front end (Streamlit)

```bash
chmod +x run_demo.sh
./run_demo.sh
```

To rebuild the complete seeded ML pipeline instead of using the included
artifacts:

```bash
.venv/bin/python run_pipeline.py
```

The redesigned prototype follows the challenge's complete decision path:

- **Executive overview** — portfolio KPIs, opportunities, separate impact metrics, segments, trends and customer drill-down.
- **Customer directory** — a searchable, downloadable view of all 5,000 synthetic customers with opportunity summaries and drill-down.
- **Opportunity desk** — evidence, confidence, estimated impact, methodology, clear action and in-session response memory.
- **Impact planner** — an inspectable deterministic baseline-vs-scenario calculator with no ML or LLM involvement.
- **Model governance** — held-out performance, baseline comparisons, feature importance and descriptive subgroup monitoring.
- **Data architecture** — live table inventory, row counts, columns, keys, relationships and executable SQL schema.
- **Risk & controls** — responsibility boundaries, grounded-generation controls, scenario handling and honest limitations.

`app.py` contains the experience. `insight_layer.py` constrains the LLM to a structured payload and rejects ungrounded numbers. `carbon_engine.py` owns all impact calculations.

## Optional Ollama wording

The app works without an LLM by using verified deterministic wording. To use
Ollama Cloud, add `OLLAMA_API_KEY`, `OLLAMA_BASE_URL=https://ollama.com`, and an
`OLLAMA_MODEL` to the git-ignored `.env` file. The supplied example defaults to
`gemma4:31b`. Local Ollama remains supported with a loopback base URL such as
`http://127.0.0.1:11434`; local requests do not need an API key.
