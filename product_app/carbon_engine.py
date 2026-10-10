"""Deterministic sustainability-impact engine (FR4).

ML and LLM code is deliberately absent. Every result is an estimated 12-month
scenario range built from versioned factors and assumptions. Missing inputs
produce ``INSUFFICIENT_DATA`` rather than an invented value.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import DATA_DIR


KM_PER_MILE = 1.609344
HORIZON_MONTHS = 12


def _references():
    factors = pd.read_csv(DATA_DIR / "emissions_factors.csv").set_index("activity")
    assumptions = pd.read_csv(DATA_DIR / "model_assumptions.csv").set_index("assumption_id")
    return factors, assumptions


FACTORS, ASSUMPTIONS = _references()
EF = FACTORS.kg_co2e_per_unit.to_dict()


def _assumption(assumption_id: str, point: str = "central") -> float:
    return float(ASSUMPTIONS.loc[assumption_id, point])


def _assumption_record(assumption_id: str, value=None) -> dict:
    row = ASSUMPTIONS.loc[assumption_id]
    return {
        "id": assumption_id,
        "value": float(row.central) if value is None else value,
        "unit": str(row.unit),
        "source": f"{row.source} ({row.version})",
    }


def _factor_record(activity: str) -> dict:
    row = FACTORS.loc[activity]
    year = None if pd.isna(row.source_year) else int(row.source_year)
    return {
        "factor_id": str(row.factor_id),
        "activity": activity,
        "kg_co2e_per_unit": float(row.kg_co2e_per_unit),
        "unit": str(row.unit),
        "source": f"{row.source} ({row.factor_version})",
        "source_year": year,
    }


def _metric(metric: str, unit: str, low: float, central: float, high: float) -> dict:
    ordered = sorted([max(0.0, float(low)), max(0.0, float(central)), max(0.0, float(high))])
    return {"metric": metric, "unit": unit, "low": round(ordered[0], 2),
            "central": round(ordered[1], 2), "high": round(ordered[2], 2)}


def _insufficient(product: str, missing: list[str], method: str) -> dict:
    return {
        "product": product,
        "status": "INSUFFICIENT_DATA",
        "is_estimate": True,
        "horizon_months": HORIZON_MONTHS,
        "horizon": "12 months",
        "method": method,
        "metrics": [],
        "assumptions": [],
        "factors": [],
        "missing_inputs": missing,
    }


def _ok(product: str, baseline: float, scenario: float, method: str, metric: dict,
        assumptions: list[dict], factors: list[dict], extra_metrics: list[dict] | None = None, **extra) -> dict:
    return {
        "product": product,
        "status": "OK",
        "is_estimate": True,
        "horizon_months": HORIZON_MONTHS,
        "horizon": "12 months",
        "method": method,
        "metrics": [metric, *(extra_metrics or [])],
        "assumptions": assumptions,
        "factors": factors,
        "missing_inputs": [],
        "baseline_kg_co2e": round(float(baseline), 1),
        "scenario_kg_co2e": round(float(scenario), 1),
        "avoided_kg_co2e_per_year": metric["central"] if metric["metric"] == "CO2E_KG" else round(float(baseline - scenario), 2),
        "estimate_low": metric["low"],
        "estimate_central": metric["central"],
        "estimate_high": metric["high"],
        **extra,
    }


def ev_finance(row) -> dict:
    method = "EV_AVOIDED_V1: current vehicle emissions minus estimated EV electricity emissions"
    missing = [key for key in ["annual_mileage", "fuel_type_code"] if pd.isna(row.get(key))]
    if missing:
        return _insufficient("EV_FINANCE", missing, method)
    annual_km = float(row["annual_mileage"]) * KM_PER_MILE
    factor_key = {0: "car_petrol", 1: "car_diesel", 2: "car_hybrid"}.get(int(row["fuel_type_code"]))
    if factor_key is None:
        return _insufficient("EV_FINANCE", ["non_EV_vehicle"], method)
    baseline = annual_km * EF[factor_key]
    grid = EF["grid_electricity"]
    scenario_central = annual_km * _assumption("A_EV_KWH_PER_KM") * grid
    low = baseline - annual_km * _assumption("A_EV_KWH_PER_KM", "high") * grid
    high = baseline - annual_km * _assumption("A_EV_KWH_PER_KM", "low") * grid
    metric = _metric("CO2E_KG", "kg CO2e per year", low, baseline - scenario_central, high)
    return _ok(
        "EV_FINANCE", baseline, scenario_central, method, metric,
        [_assumption_record("A_EV_KWH_PER_KM"),
         {"id": "A_MILEAGE_UNCHANGED", "value": True, "unit": None, "source": "Documented scenario boundary"},
         {"id": "A_MANUFACTURING_EXCLUDED", "value": True, "unit": None, "source": "Documented scenario boundary"}],
        [_factor_record(factor_key), _factor_record("grid_electricity")],
        inputs={"annual_km": round(annual_km), "factor_baseline": EF[factor_key], "grid_factor": grid},
    )


def green_home(row) -> dict:
    method = "HOME_EFFICIENCY_V1: metered energy baseline minus modelled retrofit scenario"
    missing = [key for key in ["gas_kwh_yr", "elec_kwh_yr"] if pd.isna(row.get(key))]
    if missing:
        return _insufficient("GREEN_HOME", missing, method)
    gas, electricity = float(row["gas_kwh_yr"]), float(row["elec_kwh_yr"])
    baseline = gas * EF["natural_gas"] + electricity * EF["grid_electricity"]

    def avoided(point: str) -> float:
        return gas * _assumption("A_GREEN_HOME_GAS_REDUCTION", point) * EF["natural_gas"] + \
            electricity * _assumption("A_GREEN_HOME_ELECTRICITY_REDUCTION", point) * EF["grid_electricity"]

    low, central, high = avoided("low"), avoided("central"), avoided("high")
    energy_central = gas * _assumption("A_GREEN_HOME_GAS_REDUCTION") + electricity * _assumption("A_GREEN_HOME_ELECTRICITY_REDUCTION")
    energy_low = gas * _assumption("A_GREEN_HOME_GAS_REDUCTION", "low") + electricity * _assumption("A_GREEN_HOME_ELECTRICITY_REDUCTION", "low")
    energy_high = gas * _assumption("A_GREEN_HOME_GAS_REDUCTION", "high") + electricity * _assumption("A_GREEN_HOME_ELECTRICITY_REDUCTION", "high")
    metric = _metric("CO2E_KG", "kg CO2e per year", low, central, high)
    return _ok(
        "GREEN_HOME", baseline, baseline - central, method, metric,
        [_assumption_record("A_GREEN_HOME_GAS_REDUCTION"), _assumption_record("A_GREEN_HOME_ELECTRICITY_REDUCTION")],
        [_factor_record("natural_gas"), _factor_record("grid_electricity")],
        extra_metrics=[_metric("ENERGY_KWH", "kWh per year", energy_low, energy_central, energy_high)],
        energy_saved_kwh=round(energy_central),
    )


def solar_finance(row) -> dict:
    method = "SOLAR_GENERATION_V1: modelled solar generation displaces grid electricity up to annual use"
    if pd.isna(row.get("elec_kwh_yr")):
        return _insufficient("SOLAR_FINANCE", ["elec_kwh_yr"], method)
    annual_use = float(row["elec_kwh_yr"])
    central_yield = _assumption("A_SOLAR_YIELD")
    system_kwp = float(np.clip(annual_use / central_yield, _assumption("A_SOLAR_MIN_SYSTEM"), _assumption("A_SOLAR_MAX_SYSTEM")))

    def generation(point: str) -> float:
        return min(annual_use, system_kwp * _assumption("A_SOLAR_YIELD", point))

    generated_low, generated_central, generated_high = generation("low"), generation("central"), generation("high")
    baseline = annual_use * EF["grid_electricity"]
    avoided = [generated_low * EF["grid_electricity"], generated_central * EF["grid_electricity"], generated_high * EF["grid_electricity"]]
    metric = _metric("CO2E_KG", "kg CO2e per year", *avoided)
    return _ok(
        "SOLAR_FINANCE", baseline, baseline - avoided[1], method, metric,
        [_assumption_record("A_SOLAR_YIELD"), _assumption_record("A_SOLAR_MIN_SYSTEM"), _assumption_record("A_SOLAR_MAX_SYSTEM"),
         {"id": "A_GRID_DISPLACEMENT", "value": True, "unit": None, "source": "Documented scenario boundary"}],
        [_factor_record("grid_electricity")],
        extra_metrics=[_metric("ENERGY_KWH", "kWh per year", generated_low, generated_central, generated_high)],
        system_kwp=round(system_kwp, 1), generation_kwh=round(generated_central), energy_generated_kwh=round(generated_central),
    )


def paperless(row) -> dict:
    method = "PAPER_AVOIDED_V1: paper statements moved to digital using a documented lifecycle range"
    missing = [key for key in ["paper_share", "paper_stmts_yr"] if pd.isna(row.get(key))]
    if missing:
        return _insufficient("PAPERLESS", missing, method)
    statements = float(row["paper_stmts_yr"])
    low = statements * _assumption("A_PAPER_KG_CO2E_PER_STATEMENT", "low")
    central = statements * _assumption("A_PAPER_KG_CO2E_PER_STATEMENT")
    high = statements * _assumption("A_PAPER_KG_CO2E_PER_STATEMENT", "high")
    sheets = int(statements * _assumption("A_PAPER_SHEETS_PER_STATEMENT"))
    metric = _metric("CO2E_KG", "kg CO2e per year", low, central, high)
    result = _ok(
        "PAPERLESS", central, 0, method, metric,
        [_assumption_record("A_PAPER_KG_CO2E_PER_STATEMENT"), _assumption_record("A_PAPER_SHEETS_PER_STATEMENT")],
        [_factor_record("paper_statement")],
        extra_metrics=[_metric("PAPER_SHEETS", "sheets per year", sheets, sheets, sheets),
                       _metric("DIGITAL_ADOPTION_PP", "percentage points", 100 * float(row["paper_share"]),
                               100 * float(row["paper_share"]), 100 * float(row["paper_share"]))],
        paper_statements_avoided=int(statements), paper_sheets_avoided=sheets,
        digital_adoption_shift_pp=round(100 * float(row["paper_share"]), 1),
    )
    result["avoided_kg_co2e_per_year"] = round(central, 2)
    return result


ENGINE = {"EV_FINANCE": ev_finance, "GREEN_HOME": green_home, "SOLAR_FINANCE": solar_finance, "PAPERLESS": paperless}


def estimate_impact(product: str, row) -> dict:
    return ENGINE[product](row)
