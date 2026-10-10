from datetime import date

import pytest

from carbon_engine.ev import calculate_ev_impact
from carbon_engine.schemas import EligibilityStatus, MLPayload, ProductId
from eligibility.engine import evaluate_eligibility
from recommender.gate import InvalidMLPayload, evaluate_gate, validate_ml_payload
from recommender.orchestrator import evaluate_opportunity
from recommender.priority import compute_priority


def test_invalid_ml_payload_propensity():
    with pytest.raises(InvalidMLPayload):
        validate_ml_payload({"propensity": 1.5, "confidence": 0.5, "reason_codes": []})


def test_unknown_reason_code():
    with pytest.raises(InvalidMLPayload):
        validate_ml_payload(
            {"propensity": 0.8, "confidence": 0.8, "reason_codes": ["NOT_A_REAL_CODE"]}
        )


def test_gate_blocks_low_propensity():
    ctx = {
        "customer_id": "C1",
        "cutoff_date": "2026-09-30",
        "vehicle_fuel_type": "PETROL",
        "annual_distance": 12000,
        "annual_distance_unit": "km",
        "annual_distance_source": "DECLARED",
    }
    impact = calculate_ev_impact(ctx)
    ml = MLPayload(propensity=0.2, confidence=0.9, reason_codes=["HIGH_MILEAGE"])
    gate = evaluate_gate(EligibilityStatus.ELIGIBLE, ml, impact)
    assert gate.passed is False
    assert "GATE_LOW_PROPENSITY" in gate.codes


def test_full_opportunity_ev_slice():
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
        customer_ctx,
        ml,
        ProductId.EV_FINANCE,
        p95_by_product={"EV_FINANCE": 2000.0},
        run_date=date(2026, 10, 10),
    )
    assert opp.propensity == 0.84
    assert opp.confidence == 0.71
    assert opp.reason_codes == ["HIGH_FUEL_SPEND", "HIGH_MILEAGE"]
    assert opp.gate.passed is True
    assert opp.priority.score == pytest.approx(0.84 * 0.71 * (1698.0 / 2000.0), rel=0.01)
    assert opp.impact.status.value == "estimated"
