# API Contract: Glass-Box Green Insights (Megathon X, PS1)

Source of truth for every endpoint. Backend builds to it, the dashboard builds against it (using stubs until endpoints are live), and every AI agent is told to follow it. **Change the contract first, announce it in the group chat, then change code.**

Base URL: `http://<MAC_IP>:8000`  (live docs at `/docs`, machine-readable spec at `/openapi.json`)

## 0. Conventions

- JSON bodies, `snake_case` field names, ISO dates (`2026-06-30`) and timestamps (`2026-10-10T12:00:00Z`).
- Lists return `{ "items": [...], "total": number, "limit": number, "offset": number }`. Query params `limit` (default 50, max 500) and `offset` (default 0).
- Errors on every endpoint: `{ "error": string, "code": string, "detail": any | null }` with status 400, 404, 422 or 500.
- Every number the system produces about impact is an **estimate**. Responses carry `"is_estimate": true` and a `method`.
- The **core rule** holds in every response: `propensity`, `confidence`, `reason_codes` come from ML and rules; `impact` comes only from the carbon engine; `insight.text` comes only from the LLM, built from the structured fields of the same response. The LLM never changes any other field.
- **Stubs:** while the real pipeline is being built, the backend runs with `USE_STUBS=true` and serves the example payloads in section 9. Same shapes, fake values.

### Enums

| Name | Values |
|---|---|
| `product_id` | `GP01` EV Finance, `GP02` Green Home Loan, `GP03` Solar Finance, `GP04` Paperless Banking (required); `GP05` Green Investments, `GP06` Green Loans (optional) |
| `opportunity` | `EV_FINANCE`, `GREEN_HOME_LOAN`, `SOLAR_FINANCE`, `PAPERLESS_BANKING`, `GREEN_INVESTMENTS`, `GREEN_LOANS` |
| `category` | `FUEL`, `ELECTRICITY`, `GAS`, `PUBLIC_TRANSPORT`, `HOME_IMPROVEMENT`, `AUTOMOTIVE`, `UTILITIES`, `OTHER` |
| `status` | `RECOMMENDED`, `SUPPRESSED`, `INSUFFICIENT_DATA` |
| `metric` | `CO2E_KG`, `ENERGY_KWH`, `PAPER_SHEETS`, `DIGITAL_ADOPTION_PP` (percentage points). **Reported separately, never summed.** |
| `reason_code.kind` | `DRIVER`, `GATE`, `DATA_QUALITY` |
| `split` | `train`, `validation`, `test` |

## 1. Shared objects

### ReasonCode
```json
{ "code": "HIGH_FUEL_SPEND", "kind": "DRIVER", "label": "High fuel spend", "plain_text": "You spend a lot on fuel each year." }
```
Codes come only from the fixed vocabulary in the `reason_codes` table (`GET /reason-codes`). No free text.

### Gate (product-rule check)
```json
{
  "rule_pass": true,
  "failed_rules": [ { "code": "ALREADY_EV_OWNER", "message": "Customer already drives an electric vehicle" } ],
  "rule_version": "v1",
  "note": "Subject to the institution's authorised eligibility checks"
}
```
`rule_pass` is a product-rule screen, not financial eligibility. Never call a customer "eligible" in UI or LLM text.

### Impact
```json
{
  "status": "OK",
  "is_estimate": true,
  "horizon_months": 12,
  "method": "EV_AVOIDED_V1: current fuel emissions minus electricity emissions after switching",
  "metrics": [
    { "metric": "CO2E_KG", "unit": "kg CO2e per year", "low": 800.0, "central": 1200.0, "high": 1500.0 }
  ],
  "assumptions": [ { "id": "A_EV_KWH_PER_KM", "value": 0.2, "unit": "kWh/km", "source": "..." } ],
  "factors": [ { "factor_id": "EF_GRID_KWH", "activity": "UK grid electricity", "kg_co2e_per_unit": 0.2, "unit": "kWh", "source": "DESNZ/DEFRA", "source_year": 2025 } ],
  "missing_inputs": []
}
```
If inputs are missing: `"status": "INSUFFICIENT_DATA"`, `"metrics": []`, `missing_inputs` lists the fields. Never return a guessed number. (Values above are illustrative.)

### Opportunity (the main object)
```json
{
  "customer_id": "C10001",
  "opportunity": "EV_FINANCE",
  "product_id": "GP01",
  "status": "RECOMMENDED",
  "propensity": 0.84,
  "confidence": 0.87,
  "reason_codes": [ ReasonCode, ... ],
  "gate": Gate,
  "impact": Impact,
  "insight": { "text": "...", "source": "LLM", "verified": true },
  "action": { "label": "Explore EV options", "note": "Subject to eligibility checks" },
  "rank_in_customer": 1,
  "rank_score": 0.62,
  "data_as_of": "2026-06-30",
  "model_version": "propensity-gp01-v1"
}
```
- `status = SUPPRESSED`: `propensity` is still present (for audit), `insight` is `null`, `action` is `null`, `gate.failed_rules` or `suppression_reason` explains why.
- `status = INSUFFICIENT_DATA`: shown with a low-confidence flag, `impact.status = INSUFFICIENT_DATA`.
- `insight.source` is `LLM` or `TEMPLATE` (fallback when the verifier rejects LLM text). `verified` is always `true` for anything shown to a customer.

### Ranking (decision needed, see section 10)
`rank_score = propensity × confidence × impact_index`, where `impact_index` is the central impact of the product's primary metric divided by that product's 90th-percentile impact, capped at 1. This makes products with different units comparable. Ranking is computed by the backend, not by the LLM.

## 2. System

### GET /health
returns `{ "status": "ok" }`

### GET /meta
```json
{
  "cutoff_date": "2026-06-30",
  "takeup_window_days": 90,
  "customers": 5000,
  "splits": { "train": 3500, "validation": 750, "test": 750 },
  "generator_version": "gen-v1",
  "model_versions": { "categoriser": "cat-v1", "propensity": "prop-v1" },
  "generated_at": "2026-10-10T12:00:00Z"
}
```

## 3. Catalogue and reference data

### GET /products
returns `{ "items": [ { "product_id", "product", "opportunity", "category", "required", "intended_use_case", "eligibility", "sustainability_metric", "action_label" } ] }`

### GET /reason-codes
returns `{ "items": [ ReasonCode + "product_id": string | null ] }`

### GET /emission-factors
returns `{ "items": [ { "factor_id", "activity", "unit", "kg_co2e_per_unit", "source", "source_year", "notes" } ] }`
Dashboard shows these on the "Method" panel so every figure can be traced to a source.

## 4. Customer view

### GET /customers
Query: `region`, `segment`, `search` (customer id prefix), `limit`, `offset`
returns list of
```json
{ "customer_id": "C10001", "age": 41, "income_band": "MID", "region": "North West", "home_owner": true, "split": "test", "top_opportunity": "EV_FINANCE", "top_rank_score": 0.62 }
```

### GET /customers/{customer_id}
The Customer 360 view (FR1).
```json
{
  "customer_id": "C10001",
  "profile": { "age": 41, "income_band": "MID", "postcode": "M1 1AA", "region": "North West", "home_owner": true, "digital_usage": 0.62, "sustainability_preference": "MEDIUM" },
  "features": { "fuel_spend_12m": 2100.0, "annual_mileage": 14000, "electricity_kwh_12m": 3900.0, "paper_statement_ratio": 0.8 },
  "holdings": [ { "product": "VEHICLE_LOAN", "start_date": "2024-03-01", "balance": 6400.0, "status": "ACTIVE" } ],
  "vehicle": { "vehicle_type": "CAR", "fuel_type": "PETROL", "vehicle_age": 9, "annual_mileage": 14000 },
  "data_quality": { "completeness": 0.93, "missing_fields": [] },
  "data_as_of": "2026-06-30"
}
```
404 if the customer does not exist.

### GET /customers/{customer_id}/transactions
Query: `category`, `from`, `to`, `limit`, `offset`
returns list of `{ "transaction_id", "txn_date", "merchant_description", "amount", "debit_credit", "category", "category_method": "RULE" | "ML", "category_confidence" }`

### GET /customers/{customer_id}/opportunities
Customer-facing list. Returns `RECOMMENDED` and `INSUFFICIENT_DATA` only, ordered by `rank_in_customer`. **Suppressed products never appear here.**
returns `{ "items": [ Opportunity, ... ], "data_as_of": "2026-06-30" }`

### GET /customers/{customer_id}/opportunities/{product_id}
One Opportunity, any status (this is the drill-down "Evidence → Impact → Action" step). 404 if the product was never evaluated for this customer.

### GET /customers/{customer_id}/audit
Everything the system decided, including suppressed products and why (FR7).
returns `{ "items": [ Opportunity, ... ] }` for all six products, with `status` and `gate` filled in.

### POST /customers/{customer_id}/insights/regenerate
Body: `{ "product_id": "GP01" }`
Rebuilds the structured payload, calls the LLM, runs the verifier, caches by payload hash.
returns `{ "product_id": "GP01", "insight": { "text", "source", "verified" }, "verifier": { "numbers_checked": 3, "numbers_matched": 3, "products_checked": 1, "reason_codes_checked": 2, "passed": true } }`

## 5. Ad-hoc scoring (for scenario tests)

Organisers may test missing data, conflicting signals, ruled-out products and thin data. This endpoint scores a customer that is **not** in the database and persists nothing.

### POST /score
Body: a customer snapshot. Every field except `customer_id` is optional on purpose.
```json
{
  "customer_id": "TEST-001",
  "profile": { "age": 35, "income_band": "MID", "home_owner": true, "digital_usage": 0.4, "sustainability_preference": "LOW" },
  "vehicle": { "fuel_type": "ELECTRIC", "vehicle_age": 2, "annual_mileage": null },
  "holdings": [],
  "transactions": [ { "txn_date": "2026-05-02", "merchant_description": "SHELL 4421 LONDON", "amount": 62.4, "debit_credit": "D" } ],
  "energy_usage": [ { "month": "2026-05-01", "electricity_kwh": 310, "gas_kwh": null } ],
  "digital_usage": [ { "month": "2026-05-01", "digital_statements": 0, "paper_statements": 1, "digital_transactions": 12, "branch_visits": 0 } ]
}
```
returns `{ "customer_id": "TEST-001", "items": [ Opportunity ×6 ], "data_quality": { "completeness": 0.55, "missing_fields": ["annual_mileage"] }, "data_as_of": "..." }`

Required behaviour (these are test cases):
- Electric vehicle owner, no replacement case: EV Finance is `SUPPRESSED`.
- Missing mileage or fuel data: `MISSING_MILEAGE`, `MISSING_FUEL_DATA` or `LOW_DATA_COMPLETENESS` appears in the reason codes, `confidence` drops, and `impact.status = INSUFFICIENT_DATA`.
- Conflicting signals: the gate decides, and `CONFLICTING_SIGNALS` is logged as a reason code.
- Not a home owner: GP02 and GP03 are `SUPPRESSED`.

## 6. Components exposed for transparency and evaluation

### POST /categorise
Body: `{ "items": [ { "merchant_description": "SHELL 4421 LONDON", "amount": 62.4 } ] }`
returns `{ "items": [ { "merchant_description": "...", "category": "FUEL", "method": "RULE", "confidence": 0.98, "model_version": "cat-v1" } ] }`
Exactly one category per item. Boundary decisions are in `docs/DATA_CARD.md` (pump purchases are `FUEL`; servicing, parts and tyres are `AUTOMOTIVE`; named energy suppliers map to `ELECTRICITY` or `GAS`; water and broadband are `UTILITIES`; unclear merchants fall to `OTHER`).

### POST /impact/estimate
Pure function of its inputs, same code the pipeline uses. No database reads except factors and assumptions.
Body: `{ "product_id": "GP01", "inputs": { "annual_mileage": 14000, "fuel_type": "PETROL", "fuel_spend_12m": 2100 } }`
returns `Impact`.

### GET /evaluation
Latest evaluation results for the dashboard "Evaluation" tab.
returns `{ "items": [ { "component": "PROPENSITY", "split": "validation", "metrics": { "pr_auc": 0.0, "lift_top_decile": 0.0 }, "baseline": { "pr_auc": 0.0 }, "git_commit": "abc123", "created_at": "..." } ] }`
(Numbers above are placeholders. Real values come from `evaluation_runs`.)

## 7. Business dashboard

All business endpoints accept the filters `region`, `product_id`, `min_confidence` and `split`. `split` defaults to `validation,test` (the customers the models were not trained on); pass `all` to include training customers.

### GET /business/summary
```json
{
  "customers_analysed": 1500,
  "opportunities_by_product": [ { "product_id": "GP01", "opportunity": "EV_FINANCE", "recommended": 210, "suppressed": 90, "insufficient_data": 14, "avg_propensity": 0.41 } ],
  "potential_impact": {
    "co2e_kg_per_year":      { "low": 0, "central": 0, "high": 0, "is_estimate": true },
    "energy_kwh_per_year":   { "low": 0, "central": 0, "high": 0, "is_estimate": true },
    "paper_sheets_per_year": { "low": 0, "central": 0, "high": 0, "is_estimate": true },
    "digital_adoption_pp":   { "central": 0, "is_estimate": true }
  },
  "data_as_of": "2026-06-30"
}
```
Metrics are separate keys on purpose. Digital adoption is not a carbon reduction and is never added into `co2e_kg_per_year`. (Zeros above are placeholders.)

### GET /business/segments
returns `{ "items": [ { "segment": "Suburban homeowners", "customers": 320, "top_product_id": "GP03", "avg_propensity": 0.52, "avg_confidence": 0.8, "potential_co2e_kg_central": 0, "conversion_opportunity": 0 } ] }`
Segment definitions are documented in `docs/DATA_CARD.md`.

### GET /business/regions
returns `{ "items": [ { "region": "North West", "customers": 410, "by_product": [ { "product_id": "GP01", "recommended": 55, "avg_propensity": 0.4 } ] } ] }`

### GET /business/trends
Query: `metric` (`fuel_spend`, `electricity_kwh`, `gas_kwh`, `paper_statement_share`, `digital_transactions`), `product_id` (optional), `region` (optional)
returns `{ "metric": "paper_statement_share", "points": [ { "month": "2026-01-01", "value": 0.61 } ] }`

### GET /business/queue
Next-best green conversation queue for relationship managers. `RECOMMENDED` and `INSUFFICIENT_DATA` only (insufficient data is flagged, not hidden). Ordered by `rank_score` descending.
Query: `region`, `product_id`, `min_confidence`, `limit`, `offset`
returns list of `{ "customer_id", "product_id", "opportunity", "status", "propensity", "confidence", "impact_central": { "metric": "CO2E_KG", "value": 1200.0 }, "rank_score", "low_confidence": false }`

### Drill-down chain
Customer → Opportunity → Evidence → Impact → Action is built from existing endpoints:
1. `GET /business/segments` or `/business/regions`
2. `GET /business/queue` (pick a customer)
3. `GET /customers/{id}/opportunities/{product_id}` for evidence (`reason_codes`, `gate`, `data_as_of`, `confidence`), impact (`impact`) and action (`action`)

## 8. Optional extension: customer memory (Could-have)

Memory may feed ML features, suppress repeat nudges and set timing. It may **never** change propensity, eligibility or impact, and may not let the LLM rewrite a prediction.

### POST /customers/{customer_id}/memory/events
Body: `{ "product_id": "GP01", "event_type": "DISMISSED" }` (`SHOWN`, `CLICKED`, `DISMISSED`, `ACCEPTED`)
returns `{ "event_id": 17, "recorded_at": "..." }`

### GET /customers/{customer_id}/memory
returns `{ "events": [ ... ], "suppressed_products": ["GP01"], "recomputed_ranking": [ { "product_id": "GP03", "rank_in_customer": 1, "rank_score": 0.55 } ] }`
Used by the "Month 0 / Month 3 / Month 6" demo. Gate and impact fields are unchanged between calls.

## 9. Example payload (use for stubs and mocks)

`GET /customers/C10001/opportunities/GP01`
```json
{
  "customer_id": "C10001",
  "opportunity": "EV_FINANCE",
  "product_id": "GP01",
  "status": "RECOMMENDED",
  "propensity": 0.84,
  "confidence": 0.87,
  "reason_codes": [
    { "code": "HIGH_FUEL_SPEND", "kind": "DRIVER", "label": "High fuel spend", "plain_text": "You spend a lot on fuel each year." },
    { "code": "HIGH_ANNUAL_MILEAGE", "kind": "DRIVER", "label": "High annual mileage", "plain_text": "You drive a lot of miles each year." },
    { "code": "EXISTING_VEHICLE", "kind": "DRIVER", "label": "Runs a combustion vehicle", "plain_text": "You currently run a petrol, diesel or hybrid vehicle." }
  ],
  "gate": { "rule_pass": true, "failed_rules": [], "rule_version": "v1", "note": "Subject to the institution's authorised eligibility checks" },
  "impact": {
    "status": "OK",
    "is_estimate": true,
    "horizon_months": 12,
    "method": "EV_AVOIDED_V1: current fuel emissions minus electricity emissions after switching",
    "metrics": [ { "metric": "CO2E_KG", "unit": "kg CO2e per year", "low": 800.0, "central": 1200.0, "high": 1500.0 } ],
    "assumptions": [ { "id": "A_EV_KWH_PER_KM", "value": 0.2, "unit": "kWh/km", "source": "placeholder" } ],
    "factors": [ { "factor_id": "EF_GRID_KWH", "activity": "UK grid electricity", "kg_co2e_per_unit": 0.2, "unit": "kWh", "source": "placeholder", "source_year": 2025 } ],
    "missing_inputs": []
  },
  "insight": { "text": "An EV may suit your driving. Your fuel spend and yearly mileage are high, and our estimate is that switching could cut about 800 to 1,500 kg CO2e a year. Subject to eligibility checks.", "source": "LLM", "verified": true },
  "action": { "label": "Explore EV options", "note": "Subject to eligibility checks" },
  "rank_in_customer": 1,
  "rank_score": 0.62,
  "data_as_of": "2026-06-30",
  "model_version": "propensity-gp01-v1"
}
```
All numbers here are illustrative stub values, not real emission factors.

## 10. Open decisions (team to settle in the first hour)

| # | Decision | Default if nobody objects |
|---|---|---|
| 1 | Dashboard framework | Streamlit (preferred in the brief, calls this API) |
| 2 | Cross-product ranking formula | `propensity × confidence × impact_index` as in section 1 |
| 3 | How ranges are made | Low / central / high parameter bounds from `model_assumptions` (deterministic). Seeded Monte Carlo only if time allows |
| 4 | Number of customers | 5,000 (3,500 / 750 / 750 split by customer) |
| 5 | LLM provider | One provider behind a single `llm/client.py` wrapper, with the template fallback always available |
| 6 | Region source | Postcode area mapped to UK region in the generator |

## 11. Change log

| Date | Who | Change |
|---|---|---|
| 2026-10-10 | (initial) | First version of the contract |
| 2026-10-11 | ML team | Adopted the improved green_insights ML pipeline and carbon engine. API response shapes are unchanged: engine outputs are mapped to contract metrics (low/central/high from the engine's sensitivity cases) and any non-OK engine status is returned as `INSUFFICIENT_DATA`. Paperless `impact.metrics` now holds `PAPER_SHEETS` and `DIGITAL_ADOPTION_PP` only, with no `CO2E_KG`, because no sourced paper-statement factor exists. Emission factors are exact DESNZ 2025 values. `db/schema.sql` adds nullable columns: `emission_factors` (`source_url`, `source_row_id`, `description`, `verified`, `boundary`), `customer_features` (`energy_months_observed`, `digital_months_observed`) and `recommendations` (`financial_eligibility`, `suitability_status`, `model_family`, `evidence_json`, `review_required`). New gate codes: `OUTSIDE_ILLUSTRATIVE_AGE_RULE`, `UNKNOWN_VEHICLE_FUEL`, `MISSING_SUITABILITY_DATA`. |
