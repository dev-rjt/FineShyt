"""Canonical impact records using the team's versioned 2026 reference factors."""
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd

LITRES_PER_UK_GALLON = 4.54609

def _base(status, method_id, method_name=None):
    return {"status": status, "method_id": method_id, "method_name": method_name,
            "methodology_reference": "GHG_PROTOCOL_AVOIDED_EMISSIONS",
            "time_horizon": {"value": 1, "unit": "YEAR"}, "primary_metric": None,
            "supporting_metrics": [], "assumptions": [], "emission_factors": [],
            "calculation_inputs": {}, "calculation_timestamp": None}

def _factor_records(factors, ids):
    selected = factors[factors.factor_id.isin(ids)]
    return [{"factor_id": r.factor_id, "activity": r.activity, "value": float(r.factor_value),
             "unit": f"{r.factor_unit}/{r.activity_unit}", "source": r.source,
             "source_year": int(r.source_year), "factor_version": str(r.factor_version)}
            for r in selected.itertuples(index=False)]

def canonical_impact(product, row, eligibility, factors):
    if eligibility["is_eligible"] is False:
        return _base("NOT_APPLICABLE", None)
    stamp = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(timespec="seconds")
    values = factors.set_index("factor_id").factor_value.to_dict()
    if product == "PAPERLESS_BANKING":
        if pd.isna(row.get("paper_stmts_yr")):
            return _base("INSUFFICIENT_DATA", "PAPERLESS_IMPACT_V1")
        count = float(row.paper_stmts_yr)
        out = _base("AVAILABLE", "PAPERLESS_IMPACT_V1", "Current annual paper statements moved to digital")
        out["primary_metric"] = {"metric": "PAPER_STATEMENTS_AVOIDED", "lower_estimate": count,
                                 "central_estimate": count, "upper_estimate": count, "unit": "statements/year"}
        out["supporting_metrics"] = [{"metric": "PAPER_SHEETS_AVOIDED", "value": count * 3, "unit": "sheets/year"}]
        out["assumptions"] = [{"code": "THREE_SHEETS_PER_STATEMENT", "description": "Each statement is assumed to contain three sheets."}]
        out["calculation_inputs"] = {"paper_statements_per_year": count}
        out["calculation_timestamp"] = stamp
        return out
    if product == "EV_FINANCE":
        if pd.isna(row.get("annual_mileage")) or pd.isna(row.get("fuel_type_code")):
            return _base("INSUFFICIENT_DATA", "EV_AVOIDED_EMISSIONS_V1")
        code = int(row.fuel_type_code)
        factor_id = "UK_DIESEL_2026" if code == 1 else "UK_PETROL_2026"
        mpg = row.get("vehicle_efficiency_mpg")
        mpg = float(mpg) if pd.notna(mpg) else (48.0 if code == 1 else 40.0)
        litres = float(row.annual_mileage) / mpg * LITRES_PER_UK_GALLON
        baseline = litres * values[factor_id]
        ev_kwh = float(row.annual_mileage) * .29
        ev = ev_kwh * (values["UK_GRID_ELECTRICITY_2026"] + values["UK_ELECTRICITY_TD_2026"])
        factor_ids = [factor_id, "UK_GRID_ELECTRICITY_2026", "UK_ELECTRICITY_TD_2026"]
        method, inputs = "Fuel combustion baseline minus EV grid electricity", {"annual_mileage": float(row.annual_mileage), "assumed_mpg": mpg, "fuel_litres": litres, "ev_kwh": ev_kwh}
    elif product == "GREEN_HOME_LOAN":
        if pd.isna(row.get("elec_kwh_yr")) and pd.isna(row.get("gas_kwh_yr")):
            return _base("INSUFFICIENT_DATA", "GREEN_HOME_RETROFIT_V1")
        gas = float(row.get("gas_kwh_yr")) if pd.notna(row.get("gas_kwh_yr")) else 0.0
        elec = float(row.get("elec_kwh_yr")) if pd.notna(row.get("elec_kwh_yr")) else 0.0
        baseline = gas * values["UK_NATURAL_GAS_2026"] + elec * values["UK_GRID_ELECTRICITY_2026"]
        ev = gas * .8 * values["UK_NATURAL_GAS_2026"] + elec * .95 * values["UK_GRID_ELECTRICITY_2026"]
        factor_ids = ["UK_NATURAL_GAS_2026", "UK_GRID_ELECTRICITY_2026"]
        method, inputs = "Illustrative retrofit: 20% gas and 5% electricity reduction", {"annual_gas_kwh": gas, "annual_electricity_kwh": elec}
    else:
        if pd.isna(row.get("elec_kwh_yr")):
            return _base("INSUFFICIENT_DATA", "SOLAR_GRID_DISPLACEMENT_V1")
        elec = float(row.elec_kwh_yr); generation = min(elec, 4.0 * 900.0)
        baseline = elec * values["UK_GRID_ELECTRICITY_2026"]
        ev = max(0.0, elec - generation) * values["UK_GRID_ELECTRICITY_2026"]
        factor_ids = ["UK_GRID_ELECTRICITY_2026"]
        method, inputs = "Grid electricity displaced by an illustrative 4 kWp solar system", {"annual_electricity_kwh": elec, "estimated_solar_generation_kwh": generation}
    central = max(0.0, baseline - ev)
    out = _base("AVAILABLE", {"EV_FINANCE": "EV_AVOIDED_EMISSIONS_V1", "GREEN_HOME_LOAN": "GREEN_HOME_RETROFIT_V1", "SOLAR_FINANCE": "SOLAR_GRID_DISPLACEMENT_V1"}[product], method)
    out["primary_metric"] = {"metric": "POTENTIAL_CO2E_AVOIDED", "lower_estimate": round(central*.85, 1), "central_estimate": round(central, 1), "upper_estimate": round(central*1.15, 1), "unit": "kgCO2e/year"}
    out["supporting_metrics"] = [{"metric": "BASELINE_EMISSIONS", "value": round(baseline, 1), "unit": "kgCO2e/year"}, {"metric": "SCENARIO_EMISSIONS", "value": round(ev, 1), "unit": "kgCO2e/year"}]
    out["assumptions"] = [{"code": "ILLUSTRATIVE_SCENARIO", "description": method}]
    out["emission_factors"] = _factor_records(factors, factor_ids)
    out["calculation_inputs"] = inputs; out["calculation_timestamp"] = stamp
    return out
