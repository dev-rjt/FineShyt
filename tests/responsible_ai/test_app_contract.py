from copy import deepcopy

from src.api import stubs
from src.engine import estimate_impact

from responsible_ai.contract_checks import validate_customer_response, validate_record


def test_all_app_stub_opportunities_match_api_contract_in_stub_mode():
    opportunities = [item for items in stubs.OPPS.values() for item in items]
    errors = [
        (item["customer_id"], item["product_id"], validate_record(item, allow_stub_placeholders=True))
        for item in opportunities
    ]
    assert all(not error for _, _, error in errors), errors


def test_customer_view_never_exposes_suppressed_opportunities():
    for customer_id in stubs.CUSTOMERS:
        visible = stubs.visible(customer_id)
        assert all(item["status"] != "SUPPRESSED" for item in visible)
        assert validate_customer_response(visible, allow_stub_placeholders=True) == []


def test_strict_mode_identifies_stub_impact_placeholders():
    recommended = next(
        item
        for items in stubs.OPPS.values()
        for item in items
        if item["status"] == "RECOMMENDED"
    )
    errors = validate_record(recommended)
    assert any("production provenance required" in error for error in errors)


def test_real_engine_output_matches_strict_responsible_ai_contract():
    record = deepcopy(stubs.OPPS["C10001"][0])
    factors = [
        {
            "factor_id": "UK_PETROL_2026",
            "activity": "PETROL_COMBUSTION",
            "factor_value": 2.0,
            "activity_unit": "litres",
            "source": "test-reference",
            "source_year": 2026,
        },
        {
            "factor_id": "UK_GRID_ELECTRICITY_2026",
            "activity": "GRID_ELECTRICITY_GENERATED",
            "factor_value": 0.1,
            "activity_unit": "kWh",
            "source": "test-reference",
            "source_year": 2026,
        },
    ]
    assumptions = [
        {
            "id": "A_PETROL_L_PER_100KM",
            "low": 6.0,
            "central": 7.0,
            "high": 8.0,
            "unit": "litres/100km",
            "source": "test-reference",
        },
        {
            "id": "A_EV_KWH_PER_KM",
            "low": 0.15,
            "central": 0.2,
            "high": 0.25,
            "unit": "kWh/km",
            "source": "test-reference",
        },
    ]
    record["impact"] = estimate_impact(
        "GP01",
        {"annual_mileage": 10_000, "fuel_type": "PETROL"},
        factors=factors,
        assumptions=assumptions,
    )
    assert validate_record(record) == []


def test_non_carbon_engine_output_does_not_invent_emission_factors():
    record = deepcopy(stubs.OPPS["C10001"][2])
    record["impact"] = estimate_impact(
        "GP04",
        {"paper_statements_12m": 12, "paper_statement_ratio": 0.75},
        factors=[],
        assumptions=[
            {
                "id": "A_PAPER_SHEETS_PER_STATEMENT",
                "low": 2.0,
                "central": 3.0,
                "high": 4.0,
                "unit": "sheets/statement",
                "source": "test-reference",
            }
        ],
    )
    assert record["impact"]["factors"] == []
    assert validate_record(record) == []
