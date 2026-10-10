# Team Roles and Hand-offs: Glass-Box Green Insights

Six roles. Each has one owner, one set of folders, and a short list of tables it writes. If the team is smaller, use the merge map in section 3. Names go in section 1.

## 1. Roles

| # | Role | Owner | Folders | One-line mission |
|---|---|---|---|---|
| R1 | Data and Pipeline | | `/src/data`, `/db`, `/data` | Honest synthetic data, labels, splits, Customer 360 |
| R2 | ML | | `/src/ml`, `/artifacts` | Categoriser, four propensity models, confidence, reason codes, baselines, evaluation |
| R3 | Rules and Carbon | | `/src/engine`, `/tests/engine` | Product-rule gate, carbon engine, emission factors, scenario suite |
| R4 | Backend and Recommender | | `/src/api`, `/src/common`, compose files | Endpoints from the contract, recommendation and ranking, integration server |
| R5 | LLM Insight | | `/src/llm`, `/tests/llm` | Payload, prompt, verifier, template fallback, cache, LLM evaluation set |
| R6 | Dashboard and Pitch | | `/app`, `/docs/pitch` | Streamlit customer and business views, drill-down, demo, final docs |

Integration server (the Mac) is run by whoever owns the Mac. R4 should be that person if possible, since the backend runs there.

## 2. Who owns what

### Tables

| Table | Written by | Read by |
|---|---|---|
| `customers`, `transactions`, `customer_products`, `vehicles`, `energy_usage`, `digital_usage_monthly`, `dataset_meta` | R1 | everyone |
| `gen_hidden_factors`, `transaction_labels`, `takeup_labels` | R1 | R2 for training only. **`gen_hidden_factors` is never a feature.** |
| `customer_features` (Customer 360) | R1 | R2, R3, R4 |
| `transaction_categories`, `propensity_scores`, `score_reason_codes` (DRIVER codes), `evaluation_runs` | R2 | R3, R4, R5, R6 |
| `eligibility_checks`, `impact_estimates`, `emission_factors`, `model_assumptions` | R3 | R2 (features only), R4, R5, R6 |
| `recommendations` | R4 | R5, R6 |
| `insights` | R5 | R4, R6 |
| `green_products`, `reason_codes` | R4 (shared catalogue, additions by PR) | everyone |
| `memory_events` | R4 | R2, R6 (Could-have) |

`schema.sql` is owned by R1. Anyone who needs a column asks R1 or opens a small PR, then adds a line to the contract change log.

### Python interfaces (agree now, build in parallel)

```python
# src/common/schemas.py      (R4: pydantic models that mirror docs/API_CONTRACT.md)
# src/ml/categorise.py       (R2)
def categorise(items: list[dict]) -> list[CategoryResult]
# src/ml/propensity.py       (R2)
def score(features: dict) -> dict[str, PropensityResult]   # keyed by product_id: propensity, confidence, driver reason codes
# src/engine/gate.py         (R3)
def check(snapshot: CustomerSnapshot, product_id: str) -> GateResult   # rule_pass, failed_rules, data_quality codes
# src/engine/carbon.py       (R3)
def estimate(product_id: str, inputs: dict) -> ImpactResult            # pure function: same inputs, same output
# src/llm/insight.py         (R5)
def build_payload(opportunity: Opportunity) -> dict
def generate(payload: dict) -> InsightResult                           # text, source, verified, verifier_report
# src/api/recommender.py     (R4)
def recommend(snapshot: CustomerSnapshot) -> list[Opportunity]         # gate, scores, impact, ranking, suppression
```

The same functions power the pipeline, `POST /score`, `POST /categorise` and `POST /impact/estimate`. One implementation, three entry points.

### Submission items A to I

| Item | Owner | Supporting |
|---|---|---|
| A Working prototype | R6 | R4 |
| B Source code and run instructions | R4 | all (one-command rerun) |
| C Trained models and inference code | R2 | |
| D Preprocessing pipeline and data card | R1 | R3 (factor table) |
| E LLM implementation and evaluation | R5 | |
| F Architecture diagram | R4 | R6 (must match the pipeline exactly) |
| G Evaluation report | R2 | R3 (carbon tests), R5 (LLM results), R3 (scenarios) |
| H Responsible AI note | R6 | every role sends their paragraph |
| I Test set predictions | R2 | R1 (split integrity) |

## 3. Smaller team? Merge like this

| People | Merge |
|---|---|
| 5 | R5 joins R3 (the verifier checks numbers that the carbon engine produces) |
| 4 | R3 joins R1 (rules and carbon after the data generator is stable), R5 joins R4 |
| 3 | R1 + R2 (data and models), R3 + R4 + R5 (engine, API, LLM), R6 (dashboard, pitch, docs). Cut all Should and Could items first |

## 4. What each role delivers and when

Times are hours after kickoff. Adjust to the real event length, but keep the order.

### Hour 0 to 1: everyone
- Read `API_CONTRACT.md` and settle the open decisions in its section 10.
- Copy `AGENTS.md` to the repo root. Confirm folder ownership.
- R4 makes the API run with `USE_STUBS=true` so every other role can call real URLs on day one.

### R1 Data and Pipeline
1. **H+2: mini dataset.** About 200 customers across all archetypes, loaded into Postgres. Everyone integrates against this, so speed beats realism here.
2. **H+5: full dataset.** 5,000 customers, customer-level splits, realistic noisy merchant text (store numbers, typos, truncation), hidden green-attitude and financial-readiness factors with noise driving take-up labels, UK regions from postcode areas, several months of history for trends.
3. **H+6: `customer_features`** (Customer 360) built only from data dated at or before the cutoff, plus `completeness` and `missing_fields`.
4. **Leakage audit script** (`scripts/leakage_audit.py`): checks no feature uses data after the cutoff, no split overlap, and that labels are not a copy of any single feature.
5. **`docs/DATA_CARD.md`**: sources, schema, assumptions, label rules, limitations.

### R2 ML
1. **H+3: categoriser v0.** Keyword and regex rules first, then TF-IDF with logistic regression for the long tail. Evaluate on **unseen merchants** as well as unseen customers, otherwise it just memorises names. Send the category boundary decisions (Fuel vs Automotive, Electricity/Gas vs Utilities) to R1 for `docs/DATA_CARD.md`; the contract points there.
2. **H+3: baseline scores.** Write simple baseline propensities (for example top-decile spend or rule-based scores) and their driver reason codes into `propensity_scores` and `score_reason_codes` for the mini dataset. R4, R5 and R6 can then integrate against real tables before the models are ready. The trained models replace these at H+6 with the same table and column names.
3. **H+6: four propensity models** (GP01 to GP04), XGBoost or LightGBM, calibrated, each against a simple baseline (for example top-decile spend). Metrics: PR-AUC, lift, calibration.
4. **Confidence:** a documented formula blending ensemble disagreement with data completeness. It must not behave like a second propensity.
5. **Reason codes:** map SHAP drivers to the fixed vocabulary, cross-checked against rule flags. Never free text.
6. **Write** to `transaction_categories`, `propensity_scores`, `score_reason_codes`, `evaluation_runs`. Produce the test predictions file (item I).
7. **`docs/MODEL_CARD.md`** with limitations (synthetic data, circular-label risk and what was done about it).

### R3 Rules and Carbon
1. **H+2: gate v1** (`engine/gate.py`) with the product rules from `green_products.eligibility` and the GATE and DATA_QUALITY reason codes. Writes `eligibility_checks`.
2. **H+3: emission factors and assumptions.** Fill `emission_factors` and `model_assumptions` from the official published sources (UK DESNZ/DEFRA conversion factors for fuel, grid electricity and gas), record year and unit for each. **Never type factor values from memory.** A NULL factor makes the engine return `INSUFFICIENT_DATA`, which is the safe default.
3. **H+5: carbon engine** (`engine/carbon.py`), pure functions with low / central / high ranges and named methods (avoided-emissions logic aligned with GHG Protocol guidance; PCAF only if financed emissions are reported). Each product gets documented formulas, baselines and horizon. Digital adoption stays separate from CO2e.
4. **Unit tests** with hand-worked examples (`tests/engine`).
5. **Scenario suite** (`scripts/run_scenarios.py`): EV owner with no replacement case, missing mileage or fuel data, conflicting signals, a high-propensity customer who fails a product rule. Each case is pass or fail, runnable live.
6. **`docs/CARBON_METHOD.md`**.

### R4 Backend and Recommender
1. **H+1: stub API** serving the section 9 example for every endpoint.
2. **H+2: DB wiring** with the schema loaded on first start; endpoints that only read tables go live as soon as the tables fill.
3. **H+6: recommender** combining gate, propensity, impact into `recommendations`: suppressed products are kept for the audit view and never reach `/opportunities`; ranking by the formula in the contract.
4. **Integration server duties (if on the Mac):** `git pull` after merges, `make smoke` (calls `/health`, `/meta`, one customer, one `/score`), keep the machine awake.
5. **Architecture diagram** and the one-command rerun (`make run-all`: generate data, train, score, estimate, recommend, evaluate).
6. **Performance:** pre-compute scores and impact in batch; endpoints read tables. No model inference or LLM call in the request path except `/score` and `/insights/regenerate`.

### R5 LLM Insight
1. **H+2: payload schema** (strict JSON: propensity, confidence, reason codes, impact range, gate result, data timestamp) and the template fallback.
2. **H+4: prompt** that allows only fields from the payload and requires a plain statement when data is missing; no eligibility language (always "subject to eligibility checks").
3. **H+6: verifier.** Every number, product name and reason code in the text is checked against the payload; a failure falls back to the template.
4. **Cache** by payload hash; **pre-generate** insights for all demo customers.
5. **LLM evaluation set:** about 60 payloads including missing data, conflicting signals and ruled-out products. Metrics: verified-output rate, number-match rate, forbidden-claim rate (eligibility promises), product-mapping accuracy, completeness. Write to `evaluation_runs`.
6. **Provider wrapper** (`llm/client.py`) so the provider can be swapped without touching the rest.

### R6 Dashboard and Pitch
1. **H+2: Streamlit shell** against the stub API: customer view, business view, evaluation tab, method panel.
2. **H+6: drill-down** (segment or region → queue → customer → opportunity → evidence → impact → action). Impact always labelled as an estimate with its method; CO2e, energy, paper and digital adoption on separate panels. On the business view, show total potential impact and propensity-weighted impact side by side, clearly labelled.
3. **Audit view** showing suppressed products and why.
4. **Judges' deck and demo script** (three minutes, with a recorded fallback), **`docs/RESPONSIBLE_AI.md`** assembled from each role's paragraph.

## 5. Working rhythm

- **Every 2 hours:** 10-minute integration check. Everyone pushes, the Mac owner pulls, runs `make smoke`, and the group looks at the dashboard together.
- **Blocked for more than 20 minutes?** Say so in the group chat. Don't wait.
- **Contract changes:** announce, edit `API_CONTRACT.md` and its change log, then code.
- **Feature freeze** 3 hours before the end: no new features, only fixes, seeded demo data, cached insights, rehearsal.
- **Never cut:** the gate, the verifier, the baselines.

## 6. Repo layout

```
repo/
  AGENTS.md  ROLES.md  Makefile  docker-compose.yml  .env.example
  db/schema.sql
  docs/API_CONTRACT.md  DATA_CARD.md  MODEL_CARD.md  CARBON_METHOD.md  RESPONSIBLE_AI.md  pitch/
  src/
    common/   (R4)   pydantic models mirroring the contract
    data/     (R1)   generator, feature builder
    ml/       (R2)   categoriser, propensity, confidence, reason codes
    engine/   (R3)   gate, carbon
    llm/      (R5)   payload, prompt, verifier, client
    api/      (R4)   FastAPI app, recommender
  app/        (R6)   Streamlit
  scripts/    leakage_audit.py  run_scenarios.py  seed_demo.py
  tests/
  artifacts/  trained models, evaluation reports
  data/       generated files (git-ignored if large)
```

Two changes to the earlier setup guide, owned by R4:
- The backend image must see all of `/src`. Build with the repo root as context (`build: .`) and set `PYTHONPATH=/app/src`, or mount the whole repo at `/app`.
- Mount the schema into the database container: `./db/schema.sql:/docker-entrypoint-initdb.d/01-schema.sql`. The example `Task` table from the starter skeleton goes away; `schema.sql` is the source of truth.

### Moving the starter skeleton into this layout (R4, first 30 minutes)

The first setup used `backend/app/main.py`, a second `src/main.py`, two `requirements.txt` files and a `backend/Dockerfile`. Move it like this:

1. Move the FastAPI app from `backend/app/main.py` to `src/api/main.py`. Delete the unused `src/main.py` so there is only one entry point.
2. Keep a single `requirements.txt` at the repo root. Move the Dockerfile to the repo root and delete the `backend/` folder.
3. Add an empty `__init__.py` to `src/`, `src/api/`, `src/common/`, `src/data/`, `src/ml/`, `src/engine/` and `src/llm/` so imports work.
4. Start command inside the container: `uvicorn api.main:app --host 0.0.0.0 --port 8000`, with `PYTHONPATH=/app/src`.
5. Check that `/health` and `/docs` still work, add `.env.example`, git-ignore `data/` and `.env`, then commit. Tell the team so they pull before starting.

