from carbon_engine.schemas import EligibilityStatus, ProductId
from carbon_engine.router import calculate_impact


def test_solar_impact_estimated():
    ctx = {
        "customer_id": "C_SOLAR_1",
        "cutoff_date": "2026-09-30",
        "country": "GB",
        "home_ownership": "OWNER_OUTRIGHT",
        "property_type": "HOUSE",
        "has_solar": False,
        "electricity_kwh_monthly": [100] * 12,
    }
    impact = calculate_impact(ctx, ProductId.SOLAR_FINANCE, EligibilityStatus.ELIGIBLE)
    assert impact.status.value == "estimated"
    assert impact.co2e is not None
    assert impact.co2e.central > 0
    assert impact.energy is not None
    assert "displaced_kwh" in impact.energy


def test_green_home_impact_estimated():
    ctx = {
        "customer_id": "C_GH_1",
        "cutoff_date": "2026-09-30",
        "country": "GB",
        "home_ownership": "OWNER_OUTRIGHT",
        "heating_type": "GAS_BOILER",
        "insulation_status": "NONE",
        "gas_kwh_monthly": [600, 600, 600, 700, 800, 200, 200, 220, 300, 500, 600, 700],
        "electricity_kwh_monthly": [180] * 12,
    }
    impact = calculate_impact(ctx, ProductId.GREEN_HOME, EligibilityStatus.ELIGIBLE)
    assert impact.status.value == "estimated"
    assert impact.co2e is not None
    assert impact.co2e.central > 0
    assert impact.energy is not None


def test_paperless_impact_estimated():
    ctx = {
        "customer_id": "C_PAPER_1",
        "cutoff_date": "2026-09-30",
        "country": "GB",
        "paper_statements": True,
        "statements_per_year": 12,
        "digital_logins_90d": 12,
    }
    impact = calculate_impact(ctx, ProductId.PAPERLESS_BANKING, EligibilityStatus.ELIGIBLE)
    assert impact.status.value == "estimated"
    assert impact.paper is not None
    assert impact.paper["statements_avoided"]["central"] == 12.0
    assert impact.digital_adoption is not None
