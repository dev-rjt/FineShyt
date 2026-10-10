import pytest

from engine import estimate_impact


FACTORS = [
    {"factor_id": "UK_PETROL_2026", "activity": "PETROL_COMBUSTION", "activity_unit": "litres", "factor_value": 2.0, "source": "test", "source_year": 2026},
    {"factor_id": "UK_DIESEL_2026", "activity": "DIESEL_COMBUSTION", "activity_unit": "litres", "factor_value": 2.5, "source": "test", "source_year": 2026},
    {"factor_id": "UK_GRID_ELECTRICITY_2026", "activity": "GRID_ELECTRICITY_GENERATED", "activity_unit": "kWh", "factor_value": 0.1, "source": "test", "source_year": 2026},
    {"factor_id": "UK_NATURAL_GAS_2026", "activity": "NATURAL_GAS_GROSS_CV", "activity_unit": "kWh", "factor_value": 0.2, "source": "test", "source_year": 2026},
]

ASSUMPTIONS = [
    {"id": "A_PETROL_L_PER_100KM", "low": 6.0, "central": 7.0, "high": 8.0, "unit": "litres/100km", "source": "test"},
    {"id": "A_DIESEL_L_PER_100KM", "low": 5.0, "central": 6.0, "high": 7.0, "unit": "litres/100km", "source": "test"},
    {"id": "A_HYBRID_L_PER_100KM", "low": 4.0, "central": 5.0, "high": 6.0, "unit": "litres/100km", "source": "test"},
    {"id": "A_EV_KWH_PER_KM", "low": 0.15, "central": 0.2, "high": 0.25, "unit": "kWh/km", "source": "test"},
    {"id": "A_HOME_ELECTRICITY_REDUCTION", "low": 0.05, "central": 0.1, "high": 0.15, "unit": "ratio", "source": "test"},
    {"id": "A_HOME_GAS_REDUCTION", "low": 0.1, "central": 0.2, "high": 0.3, "unit": "ratio", "source": "test"},
    {"id": "A_SOLAR_SYSTEM_KWP", "low": 2.0, "central": 3.0, "high": 4.0, "unit": "kWp", "source": "test"},
    {"id": "A_SOLAR_YIELD_KWH_PER_KWP", "low": 700.0, "central": 800.0, "high": 900.0, "unit": "kWh/kWp/year", "source": "test"},
    {"id": "A_PAPER_STATEMENTS_PER_YEAR", "value": 12.0, "unit": "statements/year", "source": "test"},
    {"id": "A_PAPER_SHEETS_PER_STATEMENT", "low": 2.0, "central": 3.0, "high": 4.0, "unit": "sheets/statement", "source": "test"},
]


def estimate(product_id, inputs, factors=FACTORS, assumptions=ASSUMPTIONS):
    return estimate_impact(product_id, inputs, factors=factors, assumptions=assumptions)


def test_ev_returns_a_contract_shaped_traceable_range():
    result = estimate("GP01", {"annual_mileage": 10_000, "vehicle_fuel_type": "PETROL"})
    assert result["status"] == "OK"
    assert result["is_estimate"] is True
    assert result["metrics"][0]["metric"] == "CO2E_KG"
    assert result["metrics"][0]["low"] <= result["metrics"][0]["central"] <= result["metrics"][0]["high"]
    assert {row["factor_id"] for row in result["factors"]} == {
        "UK_PETROL_2026", "UK_GRID_ELECTRICITY_2026"
    }


def test_missing_customer_input_never_produces_a_guessed_number():
    result = estimate("GP01", {"vehicle_fuel_type": "DIESEL"})
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["metrics"] == []
    assert result["missing_inputs"] == ["annual_mileage"]


def test_missing_reference_data_is_reported_not_invented():
    result = estimate("GP03", {"electricity_kwh_12m": 3000}, factors=[], assumptions=ASSUMPTIONS)
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["missing_inputs"] == ["reference:UK_GRID_ELECTRICITY_2026"]


def test_home_impact_keeps_energy_and_carbon_separate():
    result = estimate("GP02", {"average_monthly_electricity_kwh": 250, "average_monthly_gas_kwh": 500})
    assert [metric["metric"] for metric in result["metrics"]] == ["ENERGY_KWH", "CO2E_KG"]


def test_solar_generation_is_capped_at_customer_electricity_use():
    result = estimate("GP03", {"electricity_kwh_12m": 1000})
    energy = result["metrics"][0]
    assert energy["high"] == 1000.0


def test_paperless_does_not_claim_a_carbon_reduction():
    result = estimate("GP04", {"paper_statements_active": True, "paper_statement_ratio": 0.75})
    assert [metric["metric"] for metric in result["metrics"]] == ["PAPER_SHEETS", "DIGITAL_ADOPTION_PP"]


def test_invalid_assumption_range_is_a_configuration_error():
    bad = [dict(row) for row in ASSUMPTIONS]
    bad[0].update({"low": 8.0, "central": 7.0, "high": 6.0})
    with pytest.raises(ValueError, match="low <= central <= high"):
        estimate("GP01", {"annual_mileage": 1000, "fuel_type": "PETROL"}, assumptions=bad)
