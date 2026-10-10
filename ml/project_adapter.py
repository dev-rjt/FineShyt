"""Map the team's canonical Customer 360 dataset into the ML feature contract."""
from pathlib import Path
import numpy as np
import pandas as pd
from config import PRODUCTS

AGE_MID = {"18-24": 21, "25-34": 30, "35-44": 40, "45-54": 50, "55-64": 60, "65+": 70}
INCOME_IDX = {"UNDER_20000": 0, "20000_39999": 1, "40000_59999": 2, "60000_89999": 3, "90000_PLUS": 4}
FUEL_CODE = {"PETROL": 0, "DIESEL": 1, "HYBRID": 2, "PLUG_IN_HYBRID": 2, "ELECTRIC": 3}
URBAN = {"LONDON": 1.0, "SOUTH_EAST": .65, "MIDLANDS": .65, "NORTH_WEST": .65,
         "YORKSHIRE": .55, "SCOTLAND": .45, "WALES": .40}

def _bool(s):
    if s.dtype == bool:
        return s.astype(int)
    return s.astype(str).str.lower().map({"true": 1, "false": 0, "1": 1, "0": 0}).fillna(0).astype(int)

def adapt_customer_360(source: pd.DataFrame, products_path: Path | None = None) -> pd.DataFrame:
    s = source.set_index("customer_id")
    f = pd.DataFrame(index=s.index)
    f["age"] = s.age_band.map(AGE_MID)
    f["income_idx"] = s.income_band.map(INCOME_IDX)
    f["home_owner"] = _bool(s.home_owner)
    f["sustainability_preference"] = pd.to_numeric(s.stated_sustainability_preference, errors="coerce")
    f["urban"] = s.region.map(URBAN)
    f["region"] = s.region
    f["digital_usage"] = pd.to_numeric(s.digital_preference, errors="coerce")
    f["has_vehicle"] = _bool(s.has_vehicle)
    f["fuel_type_code"] = s.vehicle_fuel_type.map(FUEL_CODE)
    f["vehicle_type_code"] = np.where(f.has_vehicle == 1, 0.0, np.nan)
    f["vehicle_age"] = pd.to_numeric(s.vehicle_age_years, errors="coerce")
    f["annual_mileage"] = pd.to_numeric(s.annual_mileage, errors="coerce")
    f["vehicle_efficiency_mpg"] = np.nan
    f["has_solar"] = _bool(s.has_solar)
    flags = {"has_vehicle_loan": "has_vehicle_loan", "has_mortgage": "has_mortgage",
             "has_isa": "has_investment_account", "has_savings": "has_savings_account",
             "has_personal_loan": "has_personal_loan", "has_credit_card": None}
    for target, source_col in flags.items():
        f[target] = 0 if source_col is None or source_col not in s else _bool(s[source_col])
    f["total_balance"] = 0.0
    f["n_products"] = sum(f[c] for c in ["has_vehicle_loan", "has_mortgage", "has_isa", "has_savings", "has_personal_loan"])
    if products_path and Path(products_path).exists():
        p = pd.read_csv(products_path)
        p = p[(p.status == "ACTIVE") & (pd.to_datetime(p.start_date) <= pd.to_datetime(s.data_cutoff_date.iloc[0]))]
        f["total_balance"] = p.groupby("customer_id").balance.sum().reindex(f.index).fillna(0)
        f["n_products"] = p.groupby("customer_id").size().reindex(f.index).fillna(0)
        for code, gp in [("EV_FINANCE", "GP01"), ("GREEN_HOME_LOAN", "GP02"), ("SOLAR_FINANCE", "GP03"), ("PAPERLESS_BANKING", "GP04")]:
            f[f"holds_{gp}"] = f.index.isin(p[p.product_type == code].customer_id).astype(int)
    else:
        for gp in ["GP01", "GP02", "GP03", "GP04"]:
            f[f"holds_{gp}"] = 0
    f["elec_kwh_yr"] = pd.to_numeric(s.average_monthly_electricity_kwh, errors="coerce") * 12
    f["gas_kwh_yr"] = pd.to_numeric(s.average_monthly_gas_kwh, errors="coerce") * 12
    f["heating_kwh_yr"] = f.gas_kwh_yr + .3 * f.elec_kwh_yr
    # Not present in the canonical Customer 360 yet. Neutral placeholders avoid
    # dropping model columns; add the real aggregates in the data pipeline later.
    f["winter_gas_share"] = 0.0
    months = 6.0
    for cat in ["automotive", "electricity", "fuel", "gas", "home_improvement", "other", "public_transport", "utilities"]:
        f[f"spend_{cat}_m"] = pd.to_numeric(s[f"{cat}_spend_6m"], errors="coerce") / months
    f["fuel_spend_m"] = f.spend_fuel_m
    f["home_impr_spend_m"] = f.spend_home_improvement_m
    f["total_spend_m"] = pd.to_numeric(s.total_spend_6m, errors="coerce") / months
    f["fuel_share_of_spend"] = f.fuel_spend_m / (f.total_spend_m + 1e-9)
    f["n_fuel_txn"] = f.fuel_spend_m / 60.0
    f["fuel_spend_trend"] = 1.0
    f["inflow_m"] = 0.0
    f["paper_share"] = pd.to_numeric(s.paper_statements_active, errors="coerce")
    f["paper_stmts_yr"] = f.paper_share * 12
    f["digital_tx_m"] = pd.to_numeric(s.average_digital_transactions_3m, errors="coerce")
    f["branch_visits_m"] = pd.to_numeric(s.average_branch_visits_3m, errors="coerce")
    f["digital_tx_trend"] = 1.0
    f["data_timestamp"] = s.data_cutoff_date.astype(str)
    return f.reset_index()

def wide_labels(labels: pd.DataFrame, rule_frame: pd.DataFrame) -> pd.DataFrame:
    takeup = labels.pivot(index="customer_id", columns="product_code", values="take_up")
    out = pd.DataFrame(index=rule_frame.index)
    for product in PRODUCTS:
        out[f"takeup_{product}"] = takeup[product].reindex(out.index).astype(int)
        out[f"candidate_{product}"] = rule_frame[f"eligible_{product}"].astype(int)
    return out.reset_index()
