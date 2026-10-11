"""FR1 - Customer 360: one row per customer from all tables (uses PREDICTED txn categories)."""
import numpy as np, pandas as pd
from config import *
from txn_classifier import predict_categories
from data_generation import REGIONS

INCOME_IDX = {"<20k": 0, "20-35k": 1, "35-50k": 2, "50-80k": 3, "80k+": 4}
FUEL_CODE = {"petrol": 0, "diesel": 1, "hybrid": 2, "EV": 3}
VTYPE_CODE = {"hatchback": 0, "saloon": 1, "SUV": 2, "van": 3, "estate": 4}

def build_customer_360(d, vec, clf):
    d = {k: v.copy() for k, v in d.items()}
    c = d["customers"].copy()
    if c.customer_id.duplicated().any(): raise ValueError("Duplicate customer IDs")
    start = CUTOFF_DATE - pd.DateOffset(months=HISTORY_MONTHS) + pd.Timedelta(days=1)
    for name, datecol in [("transactions", "date"), ("energy", "month"), ("digital", "month")]:
        dates = pd.to_datetime(d[name][datecol], errors="coerce")
        if dates.isna().any(): raise ValueError(f"Invalid {datecol} in {name}")
        d[name] = d[name][dates.between(start, CUTOFF_DATE)].copy()
        if name != "transactions" and d[name].duplicated(["customer_id", "month"]).any():
            raise ValueError(f"Duplicate monthly rows in {name}")
    pdates = pd.to_datetime(d["products"].start_date, errors="coerce")
    d["products"] = d["products"][pdates.notna() & (pdates <= CUTOFF_DATE)].copy()
    if d["vehicles"].customer_id.duplicated().any(): raise ValueError("One current vehicle per customer required")
    c["income_idx"] = c.income_band.map(INCOME_IDX)
    area = c.postcode.str.extract(r"^([A-Z]+)")[0]
    c["urban"] = area.map(lambda a: REGIONS.get(a, ("", np.nan))[1])
    f = c.set_index("customer_id")[["age", "income_idx", "home_owner", "digital_usage", "sustainability_preference", "urban", "region"]]

    # ---- vehicles
    v = d["vehicles"].set_index("customer_id")
    f["has_vehicle"] = f.index.isin(v.index).astype(int)
    f["fuel_type_code"] = v.fuel_type.map(FUEL_CODE).reindex(f.index)
    f["vehicle_type_code"] = v.vehicle_type.map(VTYPE_CODE).reindex(f.index)
    f["vehicle_age"] = v.vehicle_age.reindex(f.index); f["annual_mileage"] = v.annual_mileage.reindex(f.index)

    # ---- products held (active)
    p = d["products"]; p = p[p.status == "active"]
    for prod, col in [("VEHICLE_LOAN", "has_vehicle_loan"), ("MORTGAGE", "has_mortgage"), ("INVESTMENT_ISA", "has_isa"),
                      ("SAVINGS", "has_savings"), ("CREDIT_CARD", "has_credit_card"), ("PERSONAL_LOAN", "has_personal_loan")]:
        f[col] = f.index.isin(p[p["product"] == prod].customer_id).astype(int)
    for gp in PRODUCT_IDS.values():
        f[f"holds_{gp}"] = f.index.isin(p[p["product"] == gp].customer_id).astype(int)
    f["total_balance"] = p.groupby("customer_id").balance.sum().reindex(f.index).fillna(0)
    f["n_products"] = p.groupby("customer_id").size().reindex(f.index).fillna(0)

    # ---- energy
    e = d["energy"]; g = e.groupby("customer_id")
    f["energy_months_observed"] = g.month.nunique().reindex(f.index).fillna(0)
    f["elec_kwh_yr"] = g.electricity_kwh.sum(min_count=HISTORY_MONTHS)
    f["gas_kwh_yr"] = g.gas_kwh.sum(min_count=HISTORY_MONTHS)
    f.loc[f.energy_months_observed < HISTORY_MONTHS, ["elec_kwh_yr", "gas_kwh_yr"]] = np.nan
    f["heating_kwh_yr"] = f.gas_kwh_yr + 0.3 * f.elec_kwh_yr
    e = e.assign(winter=e.month.str[-2:].isin(["12", "01", "02"]))
    f["winter_gas_share"] = e[e.winter].groupby("customer_id").gas_kwh.sum() / f.gas_kwh_yr

    # ---- digital
    dg = d["digital"].sort_values("month"); g = dg.groupby("customer_id")
    tot_p, tot_d = g.paper_statements.sum(), g.digital_statements.sum()
    f["digital_months_observed"] = g.month.nunique().reindex(f.index).fillna(0)
    f["paper_stmts_yr"] = tot_p.where(f.digital_months_observed == HISTORY_MONTHS)
    f["paper_share"] = tot_p / (tot_p + tot_d)
    f["digital_tx_m"] = g.digital_transactions.mean(); f["branch_visits_m"] = g.branch_visits.mean()
    last3 = dg[pd.to_datetime(dg.month) >= (CUTOFF_DATE.to_period("M") - 2).to_timestamp()].groupby("customer_id").digital_transactions.mean()
    f["digital_tx_trend"] = last3 / (f.digital_tx_m + 1e-9)

    # ---- transactions (predicted categories only - never ground truth)
    t = d["transactions"].copy()
    t["category"], t["cat_conf"] = predict_categories(t, vec, clf)
    t["date"] = pd.to_datetime(t["date"])
    deb = t[t.debit_credit == "debit"]
    sp = deb.pivot_table(index="customer_id", columns="category", values="amount", aggfunc="sum", fill_value=0) / HISTORY_MONTHS
    sp = sp.reindex(f.index).fillna(0)
    for cat in CATEGORIES:
        f[f"spend_{cat.lower().replace(' ', '_')}_m"] = sp.get(cat, 0)
    f["fuel_spend_m"] = f.spend_fuel_m; f["home_impr_spend_m"] = f.spend_home_improvement_m
    f["total_spend_m"] = sp.sum(1)
    f["fuel_share_of_spend"] = f.fuel_spend_m / (f.total_spend_m + 1e-9)
    f["n_fuel_txn"] = deb[deb.category == "Fuel"].groupby("customer_id").size().reindex(f.index).fillna(0)
    f["inflow_m"] = t[t.debit_credit == "credit"].groupby("customer_id").amount.sum().reindex(f.index).fillna(0) / HISTORY_MONTHS
    cut = CUTOFF_DATE - pd.DateOffset(months=3)
    fr = deb[deb.category == "Fuel"]
    rec = fr[fr.date > cut].groupby("customer_id").amount.sum().reindex(f.index).fillna(0) / 3
    f["fuel_spend_trend"] = rec / (f.fuel_spend_m + 1e-9)
    observed = f.index.isin(t.customer_id)
    spend_cols = [col for col in f if col.startswith("spend_")] + ["fuel_spend_m", "home_impr_spend_m", "total_spend_m", "fuel_share_of_spend", "n_fuel_txn", "inflow_m", "fuel_spend_trend"]
    f.loc[~observed, spend_cols] = np.nan  # no history is unknown, not zero activity
    f["txn_cat_mean_conf"] = t.groupby("customer_id").cat_conf.mean().reindex(f.index)
    f["data_timestamp"] = str(CUTOFF_DATE.date())
    return f.reset_index()

MODEL_FEATURES = {  # numeric inputs for the propensity models (no leakage: nothing derived from labels)
    "EV_FINANCE": ["age", "income_idx", "home_owner", "sustainability_preference", "urban", "fuel_type_code",
                   "vehicle_type_code", "vehicle_age", "annual_mileage", "has_vehicle_loan", "has_savings", "has_isa",
                   "fuel_spend_m", "fuel_share_of_spend", "n_fuel_txn", "fuel_spend_trend", "spend_public_transport_m",
                   "spend_automotive_m", "inflow_m", "digital_usage", "total_balance"],
    "GREEN_HOME": ["age", "income_idx", "home_owner", "sustainability_preference", "urban", "has_mortgage", "has_isa",
                   "elec_kwh_yr", "gas_kwh_yr", "heating_kwh_yr", "winter_gas_share", "home_impr_spend_m",
                   "spend_utilities_m", "spend_gas_m", "spend_electricity_m", "inflow_m", "total_balance", "digital_usage"],
    "SOLAR_FINANCE": ["age", "income_idx", "home_owner", "sustainability_preference", "urban", "has_mortgage", "has_isa",
                      "elec_kwh_yr", "spend_electricity_m", "home_impr_spend_m", "inflow_m", "total_balance", "digital_usage"],
    "PAPERLESS": ["age", "income_idx", "digital_usage", "sustainability_preference", "paper_share", "digital_tx_m",
                  "branch_visits_m", "digital_tx_trend", "has_credit_card", "n_products", "inflow_m"],
}
