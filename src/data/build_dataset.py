"""Build the reproducible hybrid dataset for Glass-Box Green Insights."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


SEED = 42
CUTOFF = pd.Timestamp("2026-06-30")
START = pd.Timestamp("2025-07-01")
OUTCOME_DAYS = 90
PRODUCTS = ["EV_FINANCE", "GREEN_HOME_LOAN", "SOLAR_FINANCE", "PAPERLESS_BANKING"]
CATEGORIES = [
    "FUEL", "ELECTRICITY", "GAS", "PUBLIC_TRANSPORT",
    "HOME_IMPROVEMENT", "AUTOMOTIVE", "UTILITIES", "OTHER",
]
REGIONS = ["LONDON", "SOUTH_EAST", "MIDLANDS", "NORTH_WEST", "YORKSHIRE", "SCOTLAND", "WALES"]
POSTCODES = {
    "LONDON": ["E1", "N1", "SE1", "SW1", "W1"],
    "SOUTH_EAST": ["BN1", "GU1", "OX1", "RG1"],
    "MIDLANDS": ["B1", "CV1", "LE1", "NG1"],
    "NORTH_WEST": ["L1", "M1", "PR1"],
    "YORKSHIRE": ["BD1", "LS1", "S1", "YO1"],
    "SCOTLAND": ["AB1", "EH1", "G1"],
    "WALES": ["CF1", "LL1", "SA1"],
}

ARCHETYPES = {
    "HIGH_MILEAGE_HOMEOWNER": {"weight": 0.16, "home": 0.90, "vehicle": 0.96, "mileage": 16500, "digital": 0.70, "energy": 1.10},
    "URBAN_TRANSIT_USER": {"weight": 0.15, "home": 0.35, "vehicle": 0.30, "mileage": 4500, "digital": 0.88, "energy": 0.80},
    "ENERGY_INTENSIVE_HOMEOWNER": {"weight": 0.15, "home": 0.95, "vehicle": 0.78, "mileage": 9000, "digital": 0.64, "energy": 1.55},
    "SOLAR_READY_HOMEOWNER": {"weight": 0.13, "home": 0.96, "vehicle": 0.75, "mileage": 8500, "digital": 0.77, "energy": 1.35},
    "DIGITAL_PAPER_CUSTOMER": {"weight": 0.14, "home": 0.60, "vehicle": 0.62, "mileage": 7500, "digital": 0.94, "energy": 1.00},
    "LOW_DIGITAL_ENGAGEMENT": {"weight": 0.11, "home": 0.68, "vehicle": 0.65, "mileage": 6500, "digital": 0.22, "energy": 1.00},
    "EXISTING_EV_OWNER": {"weight": 0.07, "home": 0.82, "vehicle": 1.00, "mileage": 10500, "digital": 0.86, "energy": 1.15},
    "HIGH_ENERGY_RENTER": {"weight": 0.09, "home": 0.05, "vehicle": 0.42, "mileage": 5500, "digital": 0.82, "energy": 1.35},
}

MERCHANTS = {
    "FUEL": ["SHELL SERVICE STATION", "BP CONNECT", "ESSO FORECOURT", "TEXACO FUEL"],
    "ELECTRICITY": ["OCTOPUS ENERGY ELEC", "EDF ELECTRICITY", "E.ON NEXT ELEC", "OVO ELECTRICITY"],
    "GAS": ["BRITISH GAS", "OCTOPUS ENERGY GAS", "EDF GAS", "OVO GAS"],
    "PUBLIC_TRANSPORT": ["TFL TRAVEL CHARGE", "TRAINLINE.COM", "NATIONAL RAIL", "STAGECOACH BUS"],
    "HOME_IMPROVEMENT": ["B&Q", "WICKES", "SCREWFIX", "TOOLSTATION", "LOCAL BUILDERS MERCHANT"],
    "AUTOMOTIVE": ["HALFORDS", "LOCAL GARAGE LTD", "KWIK FIT", "MOTOR PARTS DIRECT"],
    "UTILITIES": ["THAMES WATER", "VIRGIN MEDIA", "BT GROUP", "COUNCIL SERVICES"],
    "OTHER": ["TESCO STORES", "SAINSBURYS", "AMAZON MARKETPLACE", "LOCAL CAFE", "BOOTS UK"],
}


def sigmoid(value: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-value))


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, date_format="%Y-%m-%d")


def build_customers(n: int, rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    names = list(ARCHETYPES)
    weights = np.array([ARCHETYPES[x]["weight"] for x in names])
    archetypes = rng.choice(names, n, p=weights / weights.sum())
    age_bands = rng.choice(["18-24", "25-34", "35-44", "45-54", "55-64", "65+"], n, p=[0.08, 0.22, 0.23, 0.20, 0.16, 0.11])
    income_bands = rng.choice(["UNDER_20000", "20000_39999", "40000_59999", "60000_89999", "90000_PLUS"], n, p=[0.14, 0.31, 0.27, 0.18, 0.10])
    regions = rng.choice(REGIONS, n, p=[0.23, 0.18, 0.15, 0.14, 0.12, 0.10, 0.08])
    latent_green = rng.beta(2.3, 2.0, n)
    income_score = pd.Series(income_bands).map({"UNDER_20000": 0.18, "20000_39999": 0.38, "40000_59999": 0.60, "60000_89999": 0.78, "90000_PLUS": 0.92}).to_numpy()
    financial = np.clip(0.70 * income_score + 0.30 * rng.beta(2.5, 2.2, n), 0, 1)
    records = []
    hidden = []
    for idx, archetype in enumerate(archetypes, start=1):
        profile = ARCHETYPES[archetype]
        region = regions[idx - 1]
        home_owner = rng.random() < profile["home"]
        mortgage_customer = bool(home_owner and rng.random() < 0.68)
        # Deliberate stale/conflicting records support scenario-based evaluation.
        if not home_owner and rng.random() < 0.025:
            mortgage_customer = True
        digital_preference = float(np.clip(rng.normal(profile["digital"], 0.12), 0.02, 0.99))
        stated_green = float(np.clip(latent_green[idx - 1] + rng.normal(0, 0.16), 0, 1))
        if rng.random() < 0.18:
            stated_value = np.nan
        else:
            stated_value = round(stated_green, 3)
        customer_id = f"C{idx:05d}"
        records.append({
            "customer_id": customer_id,
            "age_band": age_bands[idx - 1],
            "income_band": income_bands[idx - 1],
            "postcode_area": rng.choice(POSTCODES[region]),
            "region": region,
            "home_owner": bool(home_owner),
            "property_type": rng.choice(["FLAT", "TERRACED", "SEMI_DETACHED", "DETACHED"], p=[0.32, 0.27, 0.27, 0.14]) if home_owner else "RENTED_OR_UNKNOWN",
            "mortgage_customer": mortgage_customer,
            "stated_sustainability_preference": stated_value,
            "digital_preference": round(digital_preference, 3),
            "customer_archetype": archetype,
            "customer_since": (pd.Timestamp("2008-01-01") + pd.to_timedelta(int(rng.integers(0, 6200)), unit="D")).date(),
            "record_source": "SYNTHETIC",
        })
        hidden.append({
            "customer_id": customer_id,
            "latent_green_attitude": float(latent_green[idx - 1]),
            "latent_financial_readiness": float(financial[idx - 1]),
            "profile_energy_multiplier": profile["energy"],
            "profile_vehicle_probability": profile["vehicle"],
            "profile_mileage": profile["mileage"],
        })
    return pd.DataFrame(records), pd.DataFrame(hidden)


def build_vehicles(customers: pd.DataFrame, hidden: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    h = hidden.set_index("customer_id")
    records = []
    vid = 1
    for row in customers.itertuples(index=False):
        if rng.random() >= h.loc[row.customer_id, "profile_vehicle_probability"]:
            continue
        if row.customer_archetype == "EXISTING_EV_OWNER":
            fuel = "ELECTRIC"
        else:
            fuel = rng.choice(["PETROL", "DIESEL", "HYBRID", "PLUG_IN_HYBRID", "ELECTRIC"], p=[0.51, 0.28, 0.11, 0.04, 0.06])
        mileage = max(1000, int(rng.normal(h.loc[row.customer_id, "profile_mileage"], 2600)))
        if rng.random() < 0.07:
            mileage = np.nan
        records.append({
            "vehicle_id": f"V{vid:05d}",
            "customer_id": row.customer_id,
            "vehicle_type": "CAR",
            "fuel_type": fuel if rng.random() > 0.025 else np.nan,
            "vehicle_age_years": int(rng.integers(1, 16)),
            "annual_mileage": mileage,
            "vehicle_efficiency_mpg": np.nan if fuel == "ELECTRIC" else round(float(rng.normal(44 if fuel == "DIESEL" else 39, 6)), 1),
            "ev_efficiency_kwh_per_mile": round(float(rng.normal(0.29, 0.035)), 3) if fuel == "ELECTRIC" else np.nan,
            "ownership_status": rng.choice(["OWNED", "FINANCED", "LEASED"], p=[0.54, 0.34, 0.12]),
            "record_date": CUTOFF.date(),
            "record_source": "SYNTHETIC",
        })
        vid += 1
    return pd.DataFrame(records)


def build_energy(customers: pd.DataFrame, hidden: pd.DataFrame, london: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    months = pd.date_range(START, CUTOFF, freq="MS")
    h = hidden.set_index("customer_id")
    seeds = london["scaled_monthly_kwh"].clip(80, 1500).to_numpy()
    if not len(seeds):
        seeds = np.array([280.0, 350.0, 450.0])
    records = []
    for row in customers.itertuples(index=False):
        if rng.random() < (0.06 if row.home_owner else 0.18):
            continue
        base = float(rng.choice(seeds)) * float(h.loc[row.customer_id, "profile_energy_multiplier"])
        has_solar = bool(row.home_owner and row.customer_archetype != "SOLAR_READY_HOMEOWNER" and rng.random() < 0.10)
        electric_heating = rng.random() < 0.13
        for month in months:
            season = {1: 1.18, 2: 1.14, 3: 1.06, 4: 0.98, 5: 0.94, 6: 0.91, 7: 0.90, 8: 0.91, 9: 0.95, 10: 1.02, 11: 1.10, 12: 1.18}[month.month]
            electricity = max(45, base * season * rng.lognormal(0, 0.12))
            if has_solar:
                electricity *= 0.72 if month.month in [4, 5, 6, 7, 8, 9] else 0.90
            gas = 0.0 if electric_heating else max(0, (420 * h.loc[row.customer_id, "profile_energy_multiplier"]) * ({1: 2.1, 2: 1.9, 3: 1.5, 4: 0.9, 5: 0.45, 6: 0.22, 7: 0.18, 8: 0.20, 9: 0.38, 10: 0.85, 11: 1.45, 12: 2.0}[month.month]) * rng.lognormal(0, 0.15))
            records.append({
                "customer_id": row.customer_id,
                "month": month.date(),
                "electricity_kwh": round(electricity, 2),
                "gas_kwh": round(gas, 2),
                "estimated_bill_gbp": round(electricity * 0.27 + gas * 0.07 + 24.0, 2),
                "meter_type": rng.choice(["SMART", "STANDARD"], p=[0.78, 0.22]),
                "has_solar": has_solar,
                "data_quality": "COMPLETE",
                "profile_source": "LONDON_SMART_METER_SEEDED",
            })
    energy = pd.DataFrame(records)
    if not energy.empty:
        missing_mask = rng.random(len(energy)) < 0.025
        energy.loc[missing_mask, ["electricity_kwh", "estimated_bill_gbp"]] = np.nan
        energy.loc[missing_mask, "data_quality"] = "PARTIAL"
    return energy


def build_digital(customers: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    months = pd.date_range(START, CUTOFF, freq="MS")
    records = []
    for row in customers.itertuples(index=False):
        if rng.random() < 0.04:
            continue
        paper = row.customer_archetype in ["DIGITAL_PAPER_CUSTOMER", "LOW_DIGITAL_ENGAGEMENT"] or rng.random() < 0.27
        for month in months:
            intensity = row.digital_preference
            records.append({
                "customer_id": row.customer_id,
                "month": month.date(),
                "mobile_logins": max(0, int(rng.poisson(2 + 35 * intensity))),
                "web_logins": max(0, int(rng.poisson(1 + 7 * intensity))),
                "digital_transactions": max(0, int(rng.poisson(4 + 43 * intensity))),
                "branch_visits": max(0, int(rng.poisson(2.8 * (1 - intensity)))),
                "paper_statements": int(paper),
                "digital_statements": int(not paper),
                "marketing_email_open_rate": round(float(np.clip(rng.normal(0.12 + 0.46 * intensity, 0.14), 0, 1)), 3),
                "record_source": "SYNTHETIC",
            })
    return pd.DataFrame(records)


def category_probabilities(archetype: str) -> np.ndarray:
    base = np.array([0.08, 0.04, 0.035, 0.06, 0.05, 0.055, 0.08, 0.60])
    if archetype == "HIGH_MILEAGE_HOMEOWNER": base += [0.10, 0, 0, -0.025, 0.02, 0.04, 0, -0.135]
    if archetype == "URBAN_TRANSIT_USER": base += [-0.06, 0, 0, 0.13, -0.01, -0.03, 0, -0.03]
    if archetype == "ENERGY_INTENSIVE_HOMEOWNER": base += [0, 0.045, 0.045, -0.015, 0.035, 0, 0.02, -0.13]
    if archetype == "SOLAR_READY_HOMEOWNER": base += [0, 0.055, 0.01, 0, 0.045, 0, 0.01, -0.12]
    if archetype == "EXISTING_EV_OWNER": base += [-0.065, 0.045, 0, 0.01, 0, 0.01, 0, 0]
    return np.clip(base, 0.003, None) / np.clip(base, 0.003, None).sum()


def build_transactions(customers: pd.DataFrame, uci: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    uci_desc = uci["description"].dropna().astype(str).to_numpy()
    uci_amounts = uci["amount_gbp"].clip(1, 800).to_numpy()
    records = []
    tid = 1
    days = (CUTOFF - START).days + 1
    for customer in customers.itertuples(index=False):
        count = int(np.clip(rng.poisson(38 + 24 * customer.digital_preference), 18, 120))
        probs = category_probabilities(customer.customer_archetype)
        cats = rng.choice(CATEGORIES, count, p=probs)
        for category in cats:
            source = "SYNTHETIC"
            if category == "OTHER" and rng.random() < 0.24 and len(uci_desc):
                merchant = f"ONLINE RETAIL {str(rng.choice(uci_desc))[:80]}"
                amount = float(rng.choice(uci_amounts))
                source = "UCI_ONLINE_RETAIL_II_SEEDED"
            else:
                merchant = str(rng.choice(MERCHANTS[category]))
                merchant += f" {int(rng.integers(1, 9999)):04d}"
                means = {"FUEL": 62, "ELECTRICITY": 92, "GAS": 78, "PUBLIC_TRANSPORT": 24, "HOME_IMPROVEMENT": 118, "AUTOMOTIVE": 96, "UTILITIES": 55, "OTHER": 42}
                amount = float(rng.lognormal(math.log(means[category]), 0.58))
            transaction_date = START + pd.Timedelta(days=int(rng.integers(0, days)))
            records.append({
                "transaction_id": f"T{tid:08d}",
                "customer_id": customer.customer_id,
                "transaction_date": transaction_date.date(),
                "merchant_description": merchant.upper(),
                "amount": round(float(np.clip(amount, 0.5, 2500)), 2),
                "debit_credit": "DEBIT",
                "true_category": category,
                "source_basis": source,
            })
            tid += 1
    return pd.DataFrame(records).sort_values(["customer_id", "transaction_date", "transaction_id"])


def build_base_products(customers: pd.DataFrame, vehicles: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    vehicle_customers = set(vehicles["customer_id"])
    records = []
    pid = 1
    for row in customers.itertuples(index=False):
        choices = [("CURRENT_ACCOUNT", 1.0), ("SAVINGS_ACCOUNT", 0.62), ("PERSONAL_LOAN", 0.22), ("INVESTMENT_ACCOUNT", 0.18)]
        if row.mortgage_customer:
            choices.append(("MORTGAGE", 1.0))
        if row.customer_id in vehicle_customers:
            choices.append(("VEHICLE_LOAN", 0.34))
        for product, probability in choices:
            if rng.random() > probability:
                continue
            start_date = pd.Timestamp(row.customer_since) + pd.Timedelta(days=int(rng.integers(30, max(31, (CUTOFF - pd.Timestamp(row.customer_since)).days))))
            records.append({
                "customer_product_id": f"CP{pid:07d}", "customer_id": row.customer_id,
                "product_type": product, "start_date": min(start_date, CUTOFF).date(), "end_date": np.nan,
                "balance": round(float(max(0, rng.lognormal(8.0 if product == "MORTGAGE" else 6.4, 0.8))), 2),
                "status": "ACTIVE", "record_source": "SYNTHETIC",
            })
            pid += 1
    return pd.DataFrame(records)


def customer_360(customers: pd.DataFrame, transactions: pd.DataFrame, vehicles: pd.DataFrame, energy: pd.DataFrame, digital: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    tx = transactions.copy()
    tx["transaction_date"] = pd.to_datetime(tx["transaction_date"])
    tx = tx[tx["transaction_date"] <= CUTOFF]
    six_month = tx[tx["transaction_date"] > CUTOFF - pd.Timedelta(days=183)]
    tx_pivot = six_month.pivot_table(index="customer_id", columns="true_category", values="amount", aggfunc="sum", fill_value=0)
    tx_pivot.columns = [f"{c.lower()}_spend_6m" for c in tx_pivot.columns]
    tx_count = six_month.groupby("customer_id").agg(transaction_count_6m=("transaction_id", "count"), total_spend_6m=("amount", "sum"))

    vehicle = vehicles.sort_values("record_date").groupby("customer_id").tail(1).set_index("customer_id")
    vehicle_features = pd.DataFrame(index=vehicle.index)
    vehicle_features["has_vehicle"] = True
    vehicle_features["vehicle_fuel_type"] = vehicle["fuel_type"]
    vehicle_features["vehicle_age_years"] = vehicle["vehicle_age_years"]
    vehicle_features["annual_mileage"] = vehicle["annual_mileage"]
    vehicle_features["has_existing_ev"] = vehicle["fuel_type"].eq("ELECTRIC")

    energy_agg = energy.groupby("customer_id").agg(
        average_monthly_electricity_kwh=("electricity_kwh", "mean"),
        average_monthly_gas_kwh=("gas_kwh", "mean"),
        energy_data_months=("month", "count"),
        has_solar=("has_solar", "max"),
    )
    digital_agg = digital.groupby("customer_id").agg(
        average_mobile_logins_3m=("mobile_logins", "mean"),
        average_digital_transactions_3m=("digital_transactions", "mean"),
        average_branch_visits_3m=("branch_visits", "mean"),
        paper_statements_active=("paper_statements", "max"),
        average_email_open_rate=("marketing_email_open_rate", "mean"),
        digital_data_months=("month", "count"),
    )
    product_pre = products[pd.to_datetime(products["start_date"]) <= CUTOFF]
    product_flags = pd.crosstab(product_pre["customer_id"], product_pre["product_type"]).clip(upper=1)
    product_flags.columns = [f"has_{c.lower()}" for c in product_flags.columns]

    frame = customers.set_index("customer_id").join([tx_pivot, tx_count, vehicle_features, energy_agg, digital_agg, product_flags]).reset_index()
    for category in CATEGORIES:
        col = f"{category.lower()}_spend_6m"
        if col not in frame:
            frame[col] = 0.0
        frame[col] = frame[col].fillna(0).round(2)
    for col in ["transaction_count_6m", "total_spend_6m", "energy_data_months", "digital_data_months"]:
        frame[col] = frame[col].fillna(0)
    for col in ["has_vehicle", "has_existing_ev", "has_solar"]:
        frame[col] = frame[col].eq(True)
    frame["vehicle_data_available"] = frame["has_vehicle"] & frame["vehicle_fuel_type"].notna()
    frame["energy_data_available"] = frame["energy_data_months"] >= 6
    frame["digital_data_available"] = frame["digital_data_months"] >= 6
    frame["conflicting_homeownership_signal"] = (~frame["home_owner"]) & frame.get("has_mortgage", pd.Series(False, index=frame.index)).fillna(False).astype(bool)
    frame["data_completeness"] = (
        frame[["vehicle_data_available", "energy_data_available", "digital_data_available"]].astype(float).mean(axis=1)
    ).round(3)
    frame["data_cutoff_date"] = CUTOFF.date()
    return frame


def generate_labels(features: pd.DataFrame, hidden: pd.DataFrame, vehicles: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    h = hidden.set_index("customer_id").loc[features["customer_id"]]
    x = features.set_index("customer_id")
    fuel = np.log1p(x["fuel_spend_6m"].to_numpy()) / np.log(2001)
    mileage = x["annual_mileage"].fillna(0).to_numpy() / 22000
    elec = x["average_monthly_electricity_kwh"].fillna(0).to_numpy() / 900
    gas = x["average_monthly_gas_kwh"].fillna(0).to_numpy() / 1500
    home = x["home_owner"].astype(float).to_numpy()
    digital = np.clip(x["average_mobile_logins_3m"].fillna(0).to_numpy() / 42, 0, 1)
    paper = x["paper_statements_active"].fillna(0).to_numpy()
    solar = x["has_solar"].astype(float).to_numpy()
    green = h["latent_green_attitude"].to_numpy()
    financial = h["latent_financial_readiness"].to_numpy()
    noise = lambda scale: rng.normal(0, scale, len(x))
    scores = {
        "EV_FINANCE": -3.55 + 0.75*fuel + 0.80*mileage + 0.55*financial + 0.45*green + noise(0.55),
        "GREEN_HOME_LOAN": -3.45 + 0.80*home + 0.40*gas + 0.35*elec + 0.55*financial + 0.35*green + noise(0.60),
        "SOLAR_FINANCE": -3.75 + 1.05*home + 0.65*elec + 0.50*financial + 0.45*green - 1.5*solar + noise(0.58),
        "PAPERLESS_BANKING": -2.10 + 1.25*paper + 0.85*digital + 0.35*x["average_email_open_rate"].fillna(0).to_numpy() + noise(0.55),
    }
    rows = []
    for product, score in scores.items():
        probability = sigmoid(score)
        takeup = rng.binomial(1, probability)
        for idx, customer_id in enumerate(x.index):
            date = CUTOFF + pd.Timedelta(days=int(rng.integers(1, OUTCOME_DAYS + 1))) if takeup[idx] else pd.NaT
            rows.append({
                "customer_id": customer_id, "product_code": product,
                "cutoff_date": CUTOFF.date(), "outcome_window_days": OUTCOME_DAYS,
                "take_up": int(takeup[idx]), "take_up_date": date.date() if pd.notna(date) else np.nan,
                "label_method": "LATENT_FACTORS_PLUS_NOISE_V1",
            })
    return pd.DataFrame(rows)


def append_future_products(products: pd.DataFrame, labels: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    positive = labels[labels["take_up"] == 1]
    next_id = len(products) + 1
    additions = []
    for row in positive.itertuples(index=False):
        additions.append({
            "customer_product_id": f"CP{next_id:07d}", "customer_id": row.customer_id,
            "product_type": row.product_code, "start_date": row.take_up_date, "end_date": np.nan,
            "balance": 0.0 if row.product_code == "PAPERLESS_BANKING" else round(float(rng.lognormal(8.4, 0.55)), 2),
            "status": "ACTIVE", "record_source": "SYNTHETIC_FUTURE_LABEL_EVENT",
        })
        next_id += 1
    return pd.concat([products, pd.DataFrame(additions)], ignore_index=True)


def create_splits(customers: pd.DataFrame, rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    ids = customers["customer_id"].to_numpy().copy()
    rng.shuffle(ids)
    train_end = int(len(ids) * 0.70)
    val_end = int(len(ids) * 0.85)
    return {
        "train": pd.DataFrame({"customer_id": ids[:train_end], "split": "TRAIN"}),
        "validation": pd.DataFrame({"customer_id": ids[train_end:val_end], "split": "VALIDATION"}),
        "test": pd.DataFrame({"customer_id": ids[val_end:], "split": "TEST"}),
    }


def reference_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    green_products = pd.DataFrame([
        ["GP01", "EV_FINANCE", "EV Finance", "TRANSPORT", "Finance purchase of an electric vehicle", "POTENTIAL_CO2E_AVOIDED", True],
        ["GP02", "GREEN_HOME_LOAN", "Green Home Loan", "HOME_RETROFIT", "Finance insulation, efficient heating, glazing or heat-pump upgrades", "POTENTIAL_ENERGY_AND_CO2E_REDUCTION", True],
        ["GP03", "SOLAR_FINANCE", "Solar Finance", "RENEWABLE_ENERGY", "Finance residential solar PV installation", "POTENTIAL_GRID_ELECTRICITY_DISPLACED", True],
        ["GP04", "PAPERLESS_BANKING", "Paperless Banking", "DIGITAL", "Replace paper statements with digital statements", "PAPER_AND_DIGITAL_ADOPTION", True],
    ], columns=["product_id", "product_code", "product_name", "category", "intended_use", "sustainability_metric", "active"])
    source = "https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2026"
    factors = pd.DataFrame([
        ["UK_PETROL_2026", "PETROL_COMBUSTION", "litres", 2.35372, "kg CO2e", "Scope 1", source, 2026, "2026.1"],
        ["UK_DIESEL_2026", "DIESEL_COMBUSTION", "litres", 2.66155, "kg CO2e", "Scope 1", source, 2026, "2026.1"],
        ["UK_NATURAL_GAS_2026", "NATURAL_GAS_GROSS_CV", "kWh", 0.18231, "kg CO2e", "Scope 1", source, 2026, "2026.1"],
        ["UK_GRID_ELECTRICITY_2026", "GRID_ELECTRICITY_GENERATED", "kWh", 0.13096, "kg CO2e", "Scope 2", source, 2026, "2026.1"],
        ["UK_ELECTRICITY_TD_2026", "GRID_TRANSMISSION_DISTRIBUTION", "kWh", 0.01299, "kg CO2e", "Scope 3", source, 2026, "2026.1"],
    ], columns=["factor_id", "activity", "activity_unit", "factor_value", "factor_unit", "scope", "source", "source_year", "factor_version"])
    return green_products, factors


def build_all(output_root: Path, n_customers: int, seed: int) -> None:
    rng = np.random.default_rng(seed)
    sample_dir = Path("data/external/samples")
    uci = pd.read_csv(sample_dir / "uci_online_retail_sample.csv")
    london = pd.read_csv(sample_dir / "london_smart_meter_monthly_sample.csv")
    customers, hidden = build_customers(n_customers, rng)
    vehicles = build_vehicles(customers, hidden, rng)
    energy = build_energy(customers, hidden, london, rng)
    digital = build_digital(customers, rng)
    transactions = build_transactions(customers, uci, rng)
    base_products = build_base_products(customers, vehicles, rng)
    features_pre = customer_360(customers, transactions, vehicles, energy, digital, base_products)
    labels = generate_labels(features_pre, hidden, vehicles, rng)
    products = append_future_products(base_products, labels, rng)
    features = customer_360(customers, transactions, vehicles, energy, digital, products)
    splits = create_splits(customers, rng)
    green_products, factors = reference_tables()

    write_csv(customers, output_root / "raw/customers.csv")
    write_csv(transactions, output_root / "raw/transactions.csv")
    write_csv(products, output_root / "raw/customer_products.csv")
    write_csv(vehicles, output_root / "raw/vehicles.csv")
    write_csv(energy, output_root / "raw/energy_usage.csv")
    write_csv(digital, output_root / "raw/digital_usage.csv")
    write_csv(features, output_root / "processed/customer_360.csv")
    write_csv(labels, output_root / "processed/product_takeup_labels.csv")
    write_csv(transactions[["transaction_id", "true_category"]], output_root / "processed/transaction_category_labels.csv")
    write_csv(green_products, output_root / "reference/green_products.csv")
    write_csv(factors, output_root / "reference/emission_factors.csv")
    for name, split in splits.items():
        write_csv(split, output_root / f"splits/{name}_customers.csv")

    config = {
        "dataset_version": "1.0.0", "random_seed": seed,
        "customer_count": n_customers, "feature_start_date": str(START.date()),
        "cutoff_date": str(CUTOFF.date()), "outcome_window_days": OUTCOME_DAYS,
        "required_products": PRODUCTS, "transaction_categories": CATEGORIES,
        "public_source_usage": {
            "uci_online_retail_ii": "Seeds real transaction descriptions and amount distribution for a bounded subset of OTHER transactions.",
            "london_smart_meter": "Seeds the empirical distribution of monthly household electricity consumption.",
        },
    }
    (output_root / "dataset_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(json.dumps({
        "customers": len(customers), "transactions": len(transactions), "products": len(products),
        "vehicles": len(vehicles), "energy_rows": len(energy), "digital_rows": len(digital),
        "customer_360_rows": len(features), "label_rows": len(labels),
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=Path("data"))
    parser.add_argument("--customers", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    build_all(args.output_root, args.customers, args.seed)


if __name__ == "__main__":
    main()
