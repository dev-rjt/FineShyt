"""FR4 - Deterministic, rules-based carbon engine. No ML, no LLM, no eligibility decisions.

All figures are ESTIMATES. Factors are read from emissions_factors.csv (units + sources included).
Method labels: avoided-emissions / project-style comparison of baseline vs scenario over 12 months
(in the spirit of GHG Protocol project/avoided-emissions guidance; NOT a PCAF financed-emissions calc)."""
import numpy as np, pandas as pd
from config import DATA_DIR

KM_PER_MILE = 1.609344
ASSUMPTIONS = dict(
    ev_replaces_current_vehicle_same_mileage=True, ev_embodied_emissions_excluded=True,
    green_home_gas_reduction=0.20, green_home_elec_reduction=0.05,   # retrofit/insulation scenario (ASSUMPTION)
    solar_kwp_min=2.0, solar_kwp_max=6.0, solar_target_offset=1.0,    # size to offset up to 100% of annual use
    solar_all_generation_displaces_grid=True, horizon="12 months", paper_sheets_per_statement=3)

def _ef():
    ef = pd.read_csv(DATA_DIR / "emissions_factors.csv").set_index("activity")
    return ef.kg_co2e_per_unit.to_dict()
EF = _ef()
def _insufficient(prod, missing): return dict(product=prod, status="INSUFFICIENT_DATA", missing_inputs=missing)
def _ok(prod, base, scen, method, **extra):
    return dict(product=prod, status="OK", baseline_kg_co2e=round(base, 1), scenario_kg_co2e=round(scen, 1),
                avoided_kg_co2e_per_year=round(base - scen, 1), horizon=ASSUMPTIONS["horizon"], method=method,
                is_estimate=True, **extra)

def ev_finance(r):
    miss = [k for k in ["annual_mileage", "fuel_type_code"] if pd.isna(r.get(k))]
    if miss: return _insufficient("EV_FINANCE", miss)
    km = r["annual_mileage"] * KM_PER_MILE
    fk = {0: "car_petrol", 1: "car_diesel", 2: "car_hybrid"}.get(int(r["fuel_type_code"]))
    if fk is None: return _insufficient("EV_FINANCE", ["non_EV_vehicle"])
    base = km * EF[fk]; scen = km * EF["ev_energy_intensity"] * EF["grid_electricity"]
    return _ok("EV_FINANCE", base, scen, f"baseline = km x {fk}; scenario = km x kWh/km x grid factor",
               assumptions=["EV replaces current vehicle at same mileage", "manufacturing emissions excluded"],
               inputs=dict(annual_km=round(km), factor_baseline=EF[fk], grid_factor=EF["grid_electricity"]))

def green_home(r):
    miss = [k for k in ["gas_kwh_yr", "elec_kwh_yr"] if pd.isna(r.get(k))]
    if miss: return _insufficient("GREEN_HOME_LOAN", miss)
    base = r["gas_kwh_yr"] * EF["natural_gas"] + r["elec_kwh_yr"] * EF["grid_electricity"]
    scen = r["gas_kwh_yr"] * (1 - ASSUMPTIONS["green_home_gas_reduction"]) * EF["natural_gas"] + \
           r["elec_kwh_yr"] * (1 - ASSUMPTIONS["green_home_elec_reduction"]) * EF["grid_electricity"]
    return _ok("GREEN_HOME_LOAN", base, scen, "baseline = metered kWh x factors; scenario = assumed retrofit % reduction",
               assumptions=[f"gas -{int(ASSUMPTIONS['green_home_gas_reduction']*100)}%, elec -{int(ASSUMPTIONS['green_home_elec_reduction']*100)}% (assumption)"],
               energy_saved_kwh=round(r["gas_kwh_yr"] * ASSUMPTIONS["green_home_gas_reduction"] + r["elec_kwh_yr"] * ASSUMPTIONS["green_home_elec_reduction"]))

def solar_finance(r):
    if pd.isna(r.get("elec_kwh_yr")): return _insufficient("SOLAR_FINANCE", ["elec_kwh_yr"])
    y = EF["pv_yield"]; kwp = float(np.clip(r["elec_kwh_yr"] * ASSUMPTIONS["solar_target_offset"] / y,
                                           ASSUMPTIONS["solar_kwp_min"], ASSUMPTIONS["solar_kwp_max"]))
    gen = min(float(r["elec_kwh_yr"]), kwp * y)
    base = r["elec_kwh_yr"] * EF["grid_electricity"]; scen = base - gen * EF["grid_electricity"]
    return _ok("SOLAR_FINANCE", base, scen, "avoided = PV generation x grid factor",
               assumptions=["generation (self-use + export) displaces average grid electricity", "panel manufacturing excluded"],
               system_kwp=round(kwp, 1), generation_kwh=round(gen), energy_generated_kwh=round(gen))

def paperless(r):
    if pd.isna(r.get("paper_share")): return _insufficient("PAPERLESS_BANKING", ["paper_share"])
    paper = r.get("paper_stmts_yr", np.nan)
    if pd.isna(paper): return _insufficient("PAPERLESS_BANKING", ["paper_stmts_yr"])
    kg = paper * EF["paper_statement"]
    return dict(product="PAPERLESS_BANKING", status="OK", paper_statements_avoided=int(paper),
                paper_sheets_avoided=int(paper * ASSUMPTIONS["paper_sheets_per_statement"]),
                digital_adoption_shift_pp=round(100 * r["paper_share"], 1),
                avoided_kg_co2e_per_year=round(kg, 2), horizon=ASSUMPTIONS["horizon"], is_estimate=True,
                assumptions=["Each paper statement is assumed to contain three A4 sheets plus an envelope."],
                method="avoided = paper statements x per-statement factor (ASSUMED factor). Digital adoption is reported separately and is not itself a carbon reduction")

ENGINE = dict(EV_FINANCE=ev_finance, GREEN_HOME_LOAN=green_home, SOLAR_FINANCE=solar_finance, PAPERLESS_BANKING=paperless)
def estimate_impact(product: str, row) -> dict: return ENGINE[product](row)
