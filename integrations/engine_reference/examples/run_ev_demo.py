#!/usr/bin/env python3
"""Run EV vertical slice: eligibility + carbon + recommender."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from carbon_engine.schemas import ProductId
from eligibility.engine import evaluate_eligibility
from carbon_engine.router import calculate_impact
from recommender.orchestrator import evaluate_opportunity


def main() -> None:
    customer_ctx = json.loads((ROOT / "tests" / "fixtures" / "ev_customer.json").read_text())
    ml = {
        "propensity": 0.84,
        "confidence": 0.71,
        "reason_codes": ["HIGH_FUEL_SPEND", "HIGH_MILEAGE"],
        "model_version": "ml_demo_v1",
    }
    run = date(2026, 10, 10)

    elig = evaluate_eligibility(customer_ctx, ProductId.EV_FINANCE, run_date=run)
    impact = calculate_impact(customer_ctx, ProductId.EV_FINANCE, elig.eligibility_status)
    opp = evaluate_opportunity(
        customer_ctx,
        ml,
        ProductId.EV_FINANCE,
        p95_by_product={"EV_FINANCE": 2000.0},
        run_date=run,
    )

    print("=== Eligibility ===")
    print(elig.model_dump_json(indent=2))
    print("\n=== Impact ===")
    print(impact.model_dump_json(indent=2))
    print("\n=== Opportunity ===")
    print(opp.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
