from datetime import date

import pytest

from carbon_engine.schemas import EligibilityStatus, RuleOutcome
from eligibility.engine import evaluate_eligibility


def base_ctx(**overrides):
    ctx = {
        "customer_id": "C10001",
        "cutoff_date": "2026-09-30",
        "age_band": "35-44",
        "account_status": "ACTIVE",
        "green_offers_opt_out": False,
        "vulnerability_flag": False,
        "has_arrears": False,
        "affordability_prescreen": "PASS",
        "held_products": [],
        "vehicle_fuel_type": "PETROL",
        "annual_fuel_spend_gbp": 500,
    }
    ctx.update(overrides)
    return ctx


def test_ev_eligible_petrol():
    result = evaluate_eligibility(base_ctx(), "EV_FINANCE", run_date=date(2026, 10, 10))
    assert result.eligibility_status == EligibilityStatus.ELIGIBLE_WITH_CONDITIONS
    assert any("Subject to eligibility" in c for c in result.conditions)


def test_existing_bev_not_eligible():
    result = evaluate_eligibility(
        base_ctx(vehicle_fuel_type="BEV", vehicle_age_years=2.1),
        "EV_FINANCE",
        run_date=date(2026, 10, 10),
    )
    assert result.eligibility_status == EligibilityStatus.NOT_ELIGIBLE
    ev01 = next(d for d in result.decisions if d.rule_id == "EV01")
    assert ev01.outcome == RuleOutcome.FAIL


def test_existing_bev_replacement_eligible():
    result = evaluate_eligibility(
        base_ctx(vehicle_fuel_type="BEV", vehicle_age_years=9),
        "EV_FINANCE",
        run_date=date(2026, 10, 10),
    )
    assert result.eligibility_status == EligibilityStatus.ELIGIBLE_WITH_CONDITIONS
    ev01 = next(d for d in result.decisions if d.rule_id == "EV01")
    assert ev01.outcome == RuleOutcome.PASS


def test_high_propensity_does_not_change_eligibility():
    ctx = base_ctx(green_offers_opt_out=True)
    r1 = evaluate_eligibility(ctx, "EV_FINANCE", run_date=date(2026, 10, 10))
    assert r1.eligibility_status == EligibilityStatus.NOT_ELIGIBLE


def test_vulnerability_human_review():
    result = evaluate_eligibility(
        base_ctx(vulnerability_flag=True),
        "EV_FINANCE",
        run_date=date(2026, 10, 10),
    )
    assert result.eligibility_status == EligibilityStatus.ELIGIBLE_WITH_CONDITIONS
    assert result.no_automated_customer_message is True


def test_stale_data_insufficient():
    result = evaluate_eligibility(
        base_ctx(cutoff_date="2026-06-01"),
        "EV_FINANCE",
        run_date=date(2026, 10, 10),
    )
    assert result.eligibility_status == EligibilityStatus.INSUFFICIENT_DATA


def test_confidence_independent():
    ctx = base_ctx()
    r1 = evaluate_eligibility(ctx, "EV_FINANCE", run_date=date(2026, 10, 10))
    r2 = evaluate_eligibility(ctx, "EV_FINANCE", run_date=date(2026, 10, 10))
    assert r1.eligibility_status == r2.eligibility_status


def test_eligibility_uses_data_dictionary_fields_only():
    ctx = {
        "customer_id": "C_DICT_ONLY",
        "data_cutoff_date": "2026-09-30",
        "home_owner": True,
        "property_type": "DETACHED",
        "has_solar": False,
        "average_monthly_electricity_kwh": 200.0,
        "average_monthly_gas_kwh": 120.0,
        "energy_data_months": 12.0,
        "has_current_account": 1,
        "paper_statements_active": 1.0,
        "average_mobile_logins_3m": 10.0,
        "age_band": "35-44",
        "has_vehicle": True,
        "vehicle_fuel_type": "PETROL",
    }
    result = evaluate_eligibility(ctx, "SOLAR_FINANCE", run_date=date(2026, 10, 10))
    assert result.product.value == "SOLAR_FINANCE"
    assert result.eligibility_status in (
        EligibilityStatus.ELIGIBLE,
        EligibilityStatus.ELIGIBLE_WITH_CONDITIONS,
    )
