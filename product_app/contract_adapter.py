"""Map green_insights ML and carbon-engine outputs onto docs/API_CONTRACT.md.

The carbon engine and propensity models stay unchanged. This module only reshapes their outputs:
- impacts become contract metrics (low/central/high from the engine's own sensitivity cases), any
  non-OK engine status becomes INSUFFICIENT_DATA, and factors/assumptions are read from the
  emission_factors and model_assumptions tables;
- model evidence (feature + observed value) becomes reason codes from the fixed vocabulary, used only
  when the observed value points the way the code's wording claims (a "HIGH_*" code needs a value
  above the training median).
"""
from __future__ import annotations

import pandas as pd

from carbon_engine import ASSUMPTIONS as ENGINE_ASSUMPTIONS, estimate_impact as engine_estimate
from config import DATA_DIR
from insight_layer import REASON_TEXT

HORIZON_MONTHS = 12
METHODS = {
    "EV_FINANCE": "EV_AVOIDED_V2: annual km x passenger-car factor minus annual km x EV kWh/km x grid factor",
    "GREEN_HOME": "GREEN_HOME_AVOIDED_V2: metered gas and electricity x factors, retrofit reduction scenario",
    "SOLAR_FINANCE": "SOLAR_AVOIDED_V2: min(load, PV generation x self-use fraction) x grid factor",
    "PAPERLESS": "PAPERLESS_V2: paper statements avoided x sheets per statement; no sourced carbon factor",
}
PRODUCT_ASSUMPTIONS = {
    "EV_FINANCE": ["A_EV_KWH_PER_KM"],
    "GREEN_HOME": ["A_GREEN_HOME_GAS_REDUCTION", "A_GREEN_HOME_ELECTRICITY_REDUCTION"],
    "SOLAR_FINANCE": ["A_SOLAR_YIELD", "A_SOLAR_SELF_USE_FRACTION", "A_SOLAR_MIN_SYSTEM", "A_SOLAR_MAX_SYSTEM"],
    "PAPERLESS": ["A_PAPER_SHEETS_PER_STATEMENT"],
}
# Table assumption -> carbon-engine constant; tests check the two never drift apart.
ENGINE_KEYS = {
    "A_EV_KWH_PER_KM": "ev_kwh_per_km", "A_GREEN_HOME_GAS_REDUCTION": "green_home_gas_reduction",
    "A_GREEN_HOME_ELECTRICITY_REDUCTION": "green_home_elec_reduction", "A_SOLAR_YIELD": "solar_yield_kwh_per_kwp",
    "A_SOLAR_SELF_USE_FRACTION": "solar_self_use_fraction", "A_SOLAR_MIN_SYSTEM": "solar_kwp_min",
    "A_SOLAR_MAX_SYSTEM": "solar_kwp_max", "A_PAPER_SHEETS_PER_STATEMENT": "paper_sheets_per_statement",
}

FEATURE_CODES = {
    "fuel_spend_m": "HIGH_FUEL_SPEND", "annual_mileage": "HIGH_ANNUAL_MILEAGE", "vehicle_age": "OLDER_VEHICLE",
    "has_vehicle_loan": "EXISTING_VEHICLE_LOAN", "fuel_share_of_spend": "FUEL_SHARE_OF_SPEND_HIGH",
    "n_fuel_txn": "FREQUENT_REFUELLING", "fuel_spend_trend": "RISING_FUEL_SPEND", "fuel_type_code": "ICE_VEHICLE_TYPE",
    "sustainability_preference": "HIGH_SUSTAINABILITY_PREFERENCE", "urban": "URBAN_CHARGING_ACCESS",
    "home_owner": "HOME_OWNER", "has_mortgage": "EXISTING_MORTGAGE", "has_isa": "EXISTING_INVESTMENTS",
    "elec_kwh_yr": "HIGH_ELECTRICITY_USE", "gas_kwh_yr": "HIGH_GAS_USE", "heating_kwh_yr": "HIGH_HEATING_ENERGY_USE",
    "winter_gas_share": "HIGH_WINTER_HEATING_LOAD", "home_impr_spend_m": "HOME_IMPROVEMENT_ACTIVITY",
    "spend_utilities_m": "HIGH_UTILITY_SPEND", "spend_electricity_m": "HIGH_ELECTRICITY_SPEND",
    "spend_gas_m": "HIGH_GAS_SPEND", "paper_share": "HIGH_PAPER_STATEMENT_SHARE", "digital_tx_m": "HIGH_DIGITAL_ACTIVITY",
    "branch_visits_m": "LOW_BRANCH_USE", "digital_usage": "HIGH_DIGITAL_ENGAGEMENT",
    "digital_tx_trend": "RISING_DIGITAL_ACTIVITY", "age": "AGE_PROFILE_FIT", "total_balance": "STRONG_BALANCE_PROFILE",
    "inflow_m": "STABLE_INCOME_INFLOW", "spend_public_transport_m": "PUBLIC_TRANSPORT_USER",
    "spend_automotive_m": "AUTOMOTIVE_SPEND", "vehicle_type_code": "VEHICLE_TYPE_FIT", "has_savings": "HAS_SAVINGS",
    "n_products": "MULTI_PRODUCT_CUSTOMER",
}  # income_idx is deliberately unmapped: the audit removed affordability wording.
LOW_DIRECTION = {"branch_visits_m"}
UNDIRECTED = {"age", "fuel_type_code", "vehicle_type_code"}  # describe fit or type, not a magnitude


def _tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    factors = pd.read_csv(DATA_DIR / "emissions_factors.csv").set_index("activity")
    assumptions = pd.read_csv(DATA_DIR / "model_assumptions.csv").set_index("assumption_id")
    return factors, assumptions


FACTORS, ASSUMPTION_TABLE = _tables()


def _assumption(assumption_id: str, point: str = "central") -> float:
    return float(ASSUMPTION_TABLE.loc[assumption_id, point])


def _metric(metric: str, unit: str, values) -> dict:
    low, central, high = sorted(float(v) for v in values)
    return {"metric": metric, "unit": unit, "low": round(low, 2), "central": round(central, 2), "high": round(high, 2)}


def _base(product: str, status: str, method: str, missing: list[str]) -> dict:
    return {"product": product, "status": status, "is_estimate": True, "horizon_months": HORIZON_MONTHS,
            "horizon": "12 months", "method": method, "metrics": [], "assumptions": [], "factors": [],
            "missing_inputs": missing}


def _assumption_records(product: str) -> list[dict]:
    return [{"id": key, "value": _assumption(key), "unit": str(ASSUMPTION_TABLE.loc[key, "unit"]),
             "source": f"{ASSUMPTION_TABLE.loc[key, 'source']} ({ASSUMPTION_TABLE.loc[key, 'version']})"}
            for key in PRODUCT_ASSUMPTIONS[product]]


def _factor_records(evidence: list[dict]) -> list[dict]:
    return [{"factor_id": str(FACTORS.loc[item["activity"], "factor_id"]), "activity": item["activity"],
             "kg_co2e_per_unit": float(item["value"]), "unit": str(item["unit"]),
             "source": f"{item['source']} (row {item['source_row_id']})", "source_year": int(item["source_year"])}
            for item in evidence]


def contract_impact(product: str, row) -> dict:
    """Engine result reshaped for the API, dashboard and explanations (contract fields plus display extras)."""
    raw = engine_estimate(product, row)
    if raw.get("status") != "OK":
        missing = [str(item) for item in dict.fromkeys(raw.get("missing_inputs") or ["impact_inputs"])]
        return {**_base(product, "INSUFFICIENT_DATA", METHODS[product], missing), "engine_status": raw.get("status")}
    result = _base(product, "OK", raw.get("method") or METHODS[product], [])
    result.update(assumptions=_assumption_records(product), factors=_factor_records(raw.get("factor_evidence", [])),
                  boundary=raw.get("boundary"), financial_eligibility=raw.get("financial_eligibility", "NOT_ASSESSED"))
    if product == "PAPERLESS":
        sheets, shift = raw["paper_sheets_avoided"], raw["digital_adoption_shift_pp"]
        result["metrics"] = [_metric("PAPER_SHEETS", "sheets per year", [sheets] * 3),
                             _metric("DIGITAL_ADOPTION_PP", "percentage points", [shift] * 3)]
        result.update(paper_statements_avoided=raw["paper_statements_avoided"], paper_sheets_avoided=sheets,
                      digital_adoption_shift_pp=shift, avoided_kg_co2e_per_year=None, carbon_status="INSUFFICIENT_FACTOR")
        return result
    central = raw["avoided_kg_co2e_per_year"]
    low_case, high_case = sorted(raw["sensitivity_avoided_kg_co2e"].values())  # each engine reports two cases
    co2 = _metric("CO2E_KG", "kg CO2e per year", [low_case, central, high_case])
    result["metrics"] = [co2]
    if product == "GREEN_HOME":
        gas, elec = float(row["gas_kwh_yr"]), float(row["elec_kwh_yr"])
        saved = [gas * _assumption("A_GREEN_HOME_GAS_REDUCTION", point) + elec * _assumption("A_GREEN_HOME_ELECTRICITY_REDUCTION", point)
                 for point in ("low", "central", "high")]
        result["metrics"].append(_metric("ENERGY_KWH", "kWh per year", saved))
        result["energy_saved_kwh"] = raw["energy_saved_kwh"]
    elif product == "SOLAR_FINANCE":
        load, generated = float(row["elec_kwh_yr"]), float(raw["generation_kwh"])
        onsite = [min(load, generated * _assumption("A_SOLAR_SELF_USE_FRACTION", point)) for point in ("low", "central", "high")]
        result["metrics"].append(_metric("ENERGY_KWH", "kWh per year", onsite))
        result.update(system_kwp=raw["system_kwp"], generation_kwh=raw["generation_kwh"],
                      energy_generated_kwh=raw["energy_generated_kwh"], grid_import_avoided_kwh=raw["grid_import_avoided_kwh"],
                      exported_kwh=raw["exported_kwh"])
    result.update(baseline_kg_co2e=raw["baseline_kg_co2e"], scenario_kg_co2e=raw["scenario_kg_co2e"],
                  avoided_kg_co2e_per_year=co2["central"], estimate_low=co2["low"], estimate_central=co2["central"],
                  estimate_high=co2["high"])
    return result


def contract_reasons(model, X: pd.DataFrame, top_k: int = 3) -> list[list[str]]:
    """Vocabulary reason codes for each row of X, strongest positive model evidence first."""
    reference = getattr(model, "reference", None)
    out = []
    for evidence in model.evidence(X, top_k=len(model.feats)):
        codes = []
        for item in evidence:
            feature, code = item["feature"], FEATURE_CODES.get(item["feature"])
            if code is None or code not in REASON_TEXT or code in codes:
                continue
            if reference is not None and feature not in UNDIRECTED and feature in reference.index:
                above = item["observed_value"] > float(reference[feature])
                if above == (feature in LOW_DIRECTION) or item["observed_value"] == float(reference[feature]):
                    continue
            codes.append(code)
            if len(codes) == top_k:
                break
        out.append(codes)
    return out


def engine_assumption_drift() -> dict:
    """Assumption IDs whose table value no longer matches the carbon engine constant (should be empty)."""
    return {key: (_assumption(key), ENGINE_ASSUMPTIONS[name]) for key, name in ENGINE_KEYS.items()
            if abs(_assumption(key) - float(ENGINE_ASSUMPTIONS[name])) > 1e-12}
