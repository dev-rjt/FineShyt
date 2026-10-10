# Glass-Box Green Insights — Rules, Carbon & Recommender

Deterministic **eligibility rules**, **carbon impact** calculators, and **recommender** (gate + priority ranking) for the Lloyds Megathon hackathon.

## Layout

- `eligibility/` — YAML rule DSL + financial eligibility engine
- `carbon_engine/` — impact calculators (EV vertical slice complete; other products routed)
- `recommender/` — ML payload validation, gate, `priority = propensity × confidence × impact_norm`, customer vs business views
- `config/` — rules, thresholds, reason codes
- `data/` — emissions factors and assumptions (several values marked `TO_VERIFY`)
- `app/api/carbon.py` — thin FastAPI wrapper

## Quick start

```bash
cd /home/parth/megathon
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=.
pytest -q
```

### EV end-to-end (Python)

```python
from datetime import date
from carbon_engine.schemas import ProductId
from recommender.orchestrator import evaluate_opportunity, evaluate_customer_products

customer_ctx = {
    "customer_id": "C10001",
    "cutoff_date": "2026-09-30",
    "outcome_window_days": 90,
    "age_band": "35-44",
    "account_status": "ACTIVE",
    "green_offers_opt_out": False,
    "vulnerability_flag": False,
    "has_arrears": False,
    "affordability_prescreen": "PASS",
    "held_products": [],
    "vehicle_fuel_type": "PETROL",
    "annual_distance": 12000,
    "annual_distance_unit": "km",
    "annual_distance_source": "DECLARED",
}

ml = {
    "propensity": 0.84,
    "confidence": 0.71,
    "reason_codes": ["HIGH_FUEL_SPEND", "HIGH_MILEAGE"],
    "model_version": "ml_demo_v1",
}

opp = evaluate_opportunity(
    customer_ctx, ml, ProductId.EV_FINANCE,
    p95_by_product={"EV_FINANCE": 2000.0},
    run_date=date(2026, 10, 10),
)
print(opp.model_dump_json(indent=2))
```

### API

```bash
uvicorn app.api.carbon:app --reload --app-dir .
# POST /eligibility/evaluate, /impact/calculate, /opportunities/evaluate
# POST /recommendations/customer, /recommendations/business
```

## Pipeline

```
customer_ctx + ML → eligibility → carbon (if eligible) → gate → priority → Opportunity
```

- **Customer view:** gated opportunities only (`present_to_customer`), ranked primary + secondary.
- **Business view:** gated queue for RMs; blocked list includes gate/eligibility audit hints.

## Next steps (per spec)

- Solar, Green Home, Paperless calculators
- Remaining pytest cases in spec §10
- Replace `DEV_ILLUSTRATIVE` factors with DESNZ 2026 verified values
