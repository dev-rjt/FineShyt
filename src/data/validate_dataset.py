"""Validate integrity, chronology, leakage controls and coverage of the dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


CUTOFF = pd.Timestamp("2026-06-30")
ALLOWED_CATEGORIES = {
    "FUEL", "ELECTRICITY", "GAS", "PUBLIC_TRANSPORT",
    "HOME_IMPROVEMENT", "AUTOMOTIVE", "UTILITIES", "OTHER",
}
ALLOWED_PRODUCTS = {"EV_FINANCE", "GREEN_HOME_LOAN", "SOLAR_FINANCE", "PAPERLESS_BANKING"}


def validate(root: Path) -> dict:
    customers = pd.read_csv(root / "raw/customers.csv")
    transactions = pd.read_csv(root / "raw/transactions.csv", parse_dates=["transaction_date"])
    products = pd.read_csv(root / "raw/customer_products.csv", parse_dates=["start_date"])
    vehicles = pd.read_csv(root / "raw/vehicles.csv")
    energy = pd.read_csv(root / "raw/energy_usage.csv", parse_dates=["month"])
    digital = pd.read_csv(root / "raw/digital_usage.csv", parse_dates=["month"])
    features = pd.read_csv(root / "processed/customer_360.csv")
    labels = pd.read_csv(root / "processed/product_takeup_labels.csv", parse_dates=["cutoff_date", "take_up_date"])
    tx_labels = pd.read_csv(root / "processed/transaction_category_labels.csv")
    splits = {
        name: pd.read_csv(root / f"splits/{name}_customers.csv")
        for name in ["train", "validation", "test"]
    }
    checks: list[dict] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "status": "PASS" if passed else "FAIL", "detail": detail})

    customer_ids = set(customers["customer_id"])
    check("customers_unique", customers["customer_id"].is_unique, f"{len(customers):,} customer rows")
    check("transactions_unique", transactions["transaction_id"].is_unique, f"{len(transactions):,} transaction rows")
    check("vehicles_unique", vehicles["vehicle_id"].is_unique, f"{len(vehicles):,} vehicle rows")
    check("customer_360_one_per_customer", features["customer_id"].is_unique and set(features["customer_id"]) == customer_ids, f"{len(features):,} feature rows")

    for name, frame in [("transactions", transactions), ("products", products), ("vehicles", vehicles), ("energy", energy), ("digital", digital), ("labels", labels)]:
        unknown = set(frame["customer_id"]) - customer_ids
        check(f"{name}_foreign_keys", not unknown, f"unknown customer IDs: {len(unknown)}")

    check("transaction_categories_allowed", set(transactions["true_category"]) <= ALLOWED_CATEGORIES, str(sorted(set(transactions["true_category"]))))
    check("all_categories_present", ALLOWED_CATEGORIES <= set(transactions["true_category"]), str(transactions["true_category"].value_counts().to_dict()))
    check("one_transaction_label_each", tx_labels["transaction_id"].is_unique and len(tx_labels) == len(transactions), f"{len(tx_labels):,} labels")
    check("transaction_amounts_positive", transactions["amount"].gt(0).all(), f"range {transactions['amount'].min()} to {transactions['amount'].max()}")
    check("feature_transactions_before_cutoff", transactions["transaction_date"].le(CUTOFF).all(), f"latest {transactions['transaction_date'].max().date()}")
    check("energy_before_cutoff", energy["month"].le(CUTOFF).all(), f"latest {energy['month'].max().date()}")
    check("digital_before_cutoff", digital["month"].le(CUTOFF).all(), f"latest {digital['month'].max().date()}")

    expected_label_rows = len(customers) * len(ALLOWED_PRODUCTS)
    label_pairs = labels[["customer_id", "product_code"]]
    check("one_label_per_customer_product", len(labels) == expected_label_rows and not label_pairs.duplicated().any(), f"{len(labels):,} of {expected_label_rows:,} expected")
    check("label_products_allowed", set(labels["product_code"]) == ALLOWED_PRODUCTS, str(sorted(set(labels["product_code"]))))
    positive = labels[labels["take_up"] == 1]
    label_dates_valid = positive["take_up_date"].gt(CUTOFF).all() and positive["take_up_date"].le(CUTOFF + pd.Timedelta(days=90)).all()
    check("takeup_dates_in_outcome_window", label_dates_valid, f"positive labels: {len(positive):,}")
    check("negative_labels_have_no_date", labels.loc[labels["take_up"] == 0, "take_up_date"].isna().all(), "no future date for negative labels")

    forbidden = {"take_up", "take_up_date", "eligibility", "impact", "future_product"}
    leakage_columns = forbidden & set(features.columns)
    check("no_label_columns_in_features", not leakage_columns, f"forbidden columns found: {sorted(leakage_columns)}")
    check("future_products_excluded_from_features", not any(c in features.columns for c in ["has_ev_finance", "has_green_home_loan", "has_solar_finance", "has_paperless_banking"]), "future green-product flags absent")

    split_sets = {name: set(frame["customer_id"]) for name, frame in splits.items()}
    overlap = (split_sets["train"] & split_sets["validation"]) | (split_sets["train"] & split_sets["test"]) | (split_sets["validation"] & split_sets["test"])
    union = set().union(*split_sets.values())
    check("customer_splits_disjoint", not overlap, f"overlap: {len(overlap)}")
    check("customer_splits_complete", union == customer_ids, f"covered: {len(union):,} of {len(customer_ids):,}")
    check("split_ratio", [len(splits[x]) for x in ["train", "validation", "test"]] == [3500, 750, 750] if len(customers) == 5000 else True, str({k: len(v) for k, v in splits.items()}))

    check("energy_nonnegative", energy[["electricity_kwh", "gas_kwh"]].fillna(0).ge(0).all().all(), "energy values are nonnegative")
    check("digital_nonnegative", digital[["mobile_logins", "web_logins", "digital_transactions", "branch_visits"]].ge(0).all().all(), "digital counts are nonnegative")
    check("public_uci_seed_used", transactions["source_basis"].eq("UCI_ONLINE_RETAIL_II_SEEDED").any(), f"seeded rows: {transactions['source_basis'].eq('UCI_ONLINE_RETAIL_II_SEEDED').sum():,}")
    check("public_london_seed_used", energy["profile_source"].eq("LONDON_SMART_METER_SEEDED").all(), f"seeded rows: {len(energy):,}")
    check("missing_data_scenarios_present", features["data_completeness"].lt(1).any(), f"customers below complete: {features['data_completeness'].lt(1).sum():,}")
    check("existing_ev_scenario_present", features["has_existing_ev"].astype(str).str.lower().eq("true").any(), f"existing EV customers: {features['has_existing_ev'].astype(str).str.lower().eq('true').sum():,}")

    takeup_rates = labels.groupby("product_code")["take_up"].mean().round(4).to_dict()
    category_counts = transactions["true_category"].value_counts().sort_index().to_dict()
    missingness = {
        "annual_mileage": round(float(features["annual_mileage"].isna().mean()), 4),
        "energy_profile": round(float(1 - features["energy_data_available"].astype(bool).mean()), 4),
        "digital_profile": round(float(1 - features["digital_data_available"].astype(bool).mean()), 4),
    }
    report = {
        "dataset_version": "1.0.0",
        "overall_status": "PASS" if all(x["status"] == "PASS" for x in checks) else "FAIL",
        "counts": {
            "customers": len(customers), "transactions": len(transactions), "products": len(products),
            "vehicles": len(vehicles), "energy_rows": len(energy), "digital_rows": len(digital),
            "customer_360_rows": len(features), "product_label_rows": len(labels),
        },
        "takeup_rates": takeup_rates,
        "transaction_category_counts": category_counts,
        "missingness": missingness,
        "checks": checks,
    }
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    pd.DataFrame(checks).to_csv(reports / "validation_checks.csv", index=False)

    # Stable demo cases for integration and scenario tests.
    demo = []
    existing_ev = features[features["has_existing_ev"].astype(str).str.lower().eq("true")]
    if not existing_ev.empty:
        demo.append((existing_ev.iloc[0]["customer_id"], "EXISTING_EV_SUPPRESSION"))
    missing_vehicle = features[features["annual_mileage"].isna() & features["has_vehicle"].astype(str).str.lower().eq("true")]
    if not missing_vehicle.empty:
        demo.append((missing_vehicle.iloc[0]["customer_id"], "MISSING_MILEAGE"))
    conflict = features[features["conflicting_homeownership_signal"].astype(str).str.lower().eq("true")]
    if not conflict.empty:
        demo.append((conflict.iloc[0]["customer_id"], "HOMEOWNERSHIP_CONFLICT"))
    paperless = features[(features["paper_statements_active"] == 1) & (features["average_mobile_logins_3m"] > 25)]
    if not paperless.empty:
        demo.append((paperless.iloc[0]["customer_id"], "PAPERLESS_HIGH_DIGITAL"))
    pd.DataFrame(demo, columns=["customer_id", "scenario"]).to_csv(root / "processed/demo_scenarios.csv", index=False)

    print(json.dumps(report, indent=2))
    if report["overall_status"] != "PASS":
        raise SystemExit(1)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data"))
    args = parser.parse_args()
    validate(args.root)


if __name__ == "__main__":
    main()
