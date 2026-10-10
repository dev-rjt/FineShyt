from datetime import date

import pytest

from carbon_engine.ev import calculate_ev_impact
from carbon_engine.schemas import ImpactStatus, ProductId
from carbon_engine.router import calculate_impact
from carbon_engine.schemas import EligibilityStatus


@pytest.fixture
def ev_ctx():
    return {
        "customer_id": "C10001",
        "cutoff_date": "2026-09-30",
        "country": "GB",
        "vehicle_fuel_type": "PETROL",
        "annual_distance": 12000,
        "annual_distance_unit": "km",
        "annual_distance_source": "DECLARED",
    }


def test_ev_hand_calculated_ranges(ev_ctx):
    result = calculate_ev_impact(ev_ctx)
    assert result.status == ImpactStatus.estimated
    assert result.is_estimate is True
    assert result.claim_reduction is True
    assert result.co2e is not None
    # Seed factors: petrol 0.17, grid 0.15, ev kwh 0.17/0.19/0.22, distance ±10%
    assert result.baseline.low == pytest.approx(1836.0, abs=0.02)
    assert result.baseline.central == pytest.approx(2040.0, abs=0.02)
    assert result.baseline.high == pytest.approx(2244.0, abs=0.02)
    assert result.scenario.low == pytest.approx(275.4, abs=0.02)
    assert result.scenario.central == pytest.approx(342.0, abs=0.02)
    assert result.scenario.high == pytest.approx(435.6, abs=0.02)
    assert result.co2e.low == pytest.approx(1400.4, abs=0.02)
    assert result.co2e.central == pytest.approx(1698.0, abs=0.02)
    assert result.co2e.high == pytest.approx(1968.6, abs=0.02)


def test_ev_zero_distance_valid_zero(ev_ctx):
    ev_ctx["annual_distance"] = 0
    result = calculate_ev_impact(ev_ctx)
    assert result.status == ImpactStatus.estimated
    assert result.co2e.central == 0.0


def test_ev_missing_distance_insufficient(ev_ctx):
    del ev_ctx["annual_distance"]
    result = calculate_ev_impact(ev_ctx)
    assert result.status == ImpactStatus.insufficient_data
    assert "IMPACT_MISSING_ANNUAL_DISTANCE" in result.reason_codes
    assert result.co2e is None


def test_ev_spend_derived(ev_ctx):
    del ev_ctx["annual_distance"]
    ev_ctx["annual_fuel_spend_gbp"] = 2000
    result = calculate_ev_impact(ev_ctx)
    assert result.status == ImpactStatus.estimated
    assert result.input_quality == "SPEND_DERIVED"
    assert "DISTANCE_DERIVED_FROM_SPEND" in result.limitations


def test_ev_blocked_when_not_eligible(ev_ctx):
    impact = calculate_impact(ev_ctx, ProductId.EV_FINANCE, EligibilityStatus.NOT_ELIGIBLE)
    assert impact.status == ImpactStatus.not_applicable
    assert "BLOCKED_BY_ELIGIBILITY" in impact.reason_codes


def test_ev_reproducible(ev_ctx):
    a = calculate_ev_impact(ev_ctx).model_dump(exclude={"calculated_at"})
    b = calculate_ev_impact(ev_ctx).model_dump(exclude={"calculated_at"})
    assert a == b


def test_no_saved_wording(ev_ctx):
    result = calculate_ev_impact(ev_ctx)
    blob = result.model_dump_json()
    assert "saved" not in blob.lower()
    assert "will save" not in blob.lower()
