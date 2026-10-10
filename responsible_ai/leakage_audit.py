"""Fail-closed lineage, customer-split, cutoff and target-leakage diagnostics."""
import argparse
from pathlib import Path

import pandas as pd

from responsible_ai.features_loader import BANNED_FOR_MODELS, load_features


def _check(name, ok, detail):
    return {"check": name, "status": "PASS" if ok else "FAIL", "detail": detail}


def audit_feature_tables(tables):
    return [_check("features:" + name,
                   not bool(BANNED_FOR_MODELS.intersection(table.columns)),
                   "Banned columns excluded" if not BANNED_FOR_MODELS.intersection(table.columns)
                   else "Banned columns present") for name, table in tables.items()]


def audit_splits(customers, splits):
    sets = {name: set(table.customer_id) for name, table in splits.items()}
    names = list(sets)
    overlap = any(sets[a] & sets[b] for i, a in enumerate(names) for b in names[i + 1:])
    valid = (set(sets) == {"TRAIN", "VALIDATION", "TEST"}
             and customers.customer_id.notna().all()
             and customers.customer_id.is_unique)
    for name, table in splits.items():
        valid &= (table.customer_id.notna().all() and table.customer_id.is_unique
                  and "split" in table and table["split"].eq(name).all())
    coverage = set().union(*sets.values()) == set(customers.customer_id)
    return _check("customer_splits", bool(valid and not overlap and coverage),
                  "Unique, disjoint, complete customer partition required")


def audit_dates(customer_360, tables):
    cutoff = customer_360.set_index("customer_id")["data_cutoff_date"]
    if not cutoff.index.is_unique or cutoff.isna().any():
        return [_check("feature_dates", False, "Cutoff key or dates invalid")]
    cutoff_dates = pd.to_datetime(cutoff, errors="coerce", utc=True)
    results = []
    for name, table in tables.items():
        for field in ("transaction_date", "month", "record_date"):
            if field not in table:
                continue
            dates = pd.to_datetime(table[field], errors="coerce", utc=True)
            limits = pd.to_datetime(table.customer_id.map(cutoff), errors="coerce", utc=True)
            ok = dates.notna() & limits.notna() & dates.le(limits)
            results.append(_check("dates:" + name + ":" + field, bool(ok.all()),
                                  f"{int((~ok).sum())} missing, invalid, unmapped or future dates"))
    results.append(_check("cutoff_dates", bool(cutoff_dates.notna().all()),
                          "All customers need valid cutoff dates"))
    return results


def audit_labels(labels, customer_360, features):
    required = {"customer_id", "product_code", "cutoff_date", "outcome_window_days",
                "take_up", "take_up_date", "label_method"}
    if not required <= set(labels):
        return [_check("label_structure", False, "Required label columns missing")], []
    cutoff = pd.to_datetime(labels.cutoff_date, errors="coerce", utc=True)
    dates = pd.to_datetime(labels.take_up_date, errors="coerce", utc=True)
    days = pd.to_numeric(labels.outcome_window_days, errors="coerce")
    binary = labels.take_up.isin([0, 1]) & labels.take_up.notna()
    positive = labels.take_up.eq(1)
    delta = (dates - cutoff).dt.total_seconds() / 86400
    valid_date = (~positive & labels.take_up_date.isna()) | (
        positive & dates.notna() & delta.gt(0) & delta.le(days))
    feature_cutoff = customer_360.set_index("customer_id").data_cutoff_date
    cutoff_match = labels.customer_id.map(feature_cutoff).eq(labels.cutoff_date)
    valid = binary & cutoff.notna() & days.gt(0) & days.mod(1).eq(0) & valid_date & cutoff_match
    method = labels.label_method.notna() & labels.label_method.astype(str).str.strip().ne("")
    products = {"EV_FINANCE", "GREEN_HOME_LOAN", "SOLAR_FINANCE", "PAPERLESS_BANKING"}
    results = [
        _check("label_window", bool(valid.all()), f"{int((~valid).sum())} invalid label rows"),
        _check("label_method", bool(method.all()), "Nonempty label provenance required"),
        _check("label_keys", not labels.duplicated(["customer_id", "product_code"]).any()
               and labels.product_code.isin(products).all(), "Unique customer/product labels required"),
    ]
    if len(features) != len(customer_360) or not customer_360.customer_id.is_unique:
        results.append(_check("label_alignment", False, "Feature rows cannot be aligned"))
        return results, []
    aligned = features.reset_index(drop=True).copy()
    aligned["customer_id"] = customer_360.customer_id.to_numpy()  # Audit join key only.
    correlations = []
    for product, group in labels.groupby("product_code"):
        joined = group.merge(aligned, on="customer_id", how="left", validate="many_to_one")
        leak = False
        for feature in features.columns:
            x, y = joined[feature], joined.take_up
            copied = x.notna().all() and (x.eq(y).all() or x.astype(str).equals(y.astype(str)))
            correlation = None
            if pd.api.types.is_numeric_dtype(x):
                paired = pd.DataFrame({"x": x.astype(float), "y": y}).dropna()
                if len(paired) >= 3 and paired.x.nunique() > 1 and paired.y.nunique() > 1:
                    correlation = float(paired.x.corr(paired.y))
                correlations.append({"product_code": product, "label": "take_up",
                                     "feature": feature, "correlation": correlation,
                                     "observations": len(paired)})
            leak |= copied or (correlation is not None and abs(correlation) > 0.9)
        results.append(_check("label_feature_copy:" + product, not leak,
                              "Exact feature copies and absolute Pearson correlation > 0.9 are flagged"))
    return results, correlations


def audit_transaction_labels(transactions, labels, features):
    if not transactions.transaction_id.is_unique or not labels.transaction_id.is_unique:
        return _check("transaction_labels", False, "Transaction label keys must be unique")
    joined = transactions[["transaction_id"]].merge(labels, on="transaction_id", how="left",
                                                    validate="one_to_one")
    ok = set(transactions.transaction_id) == set(labels.transaction_id) and joined.true_category.notna().all()
    for column in features:
        ok &= not features[column].reset_index(drop=True).astype(str).equals(joined.true_category.astype(str))
    return _check("transaction_labels", bool(ok), "Coverage and exact category-to-feature copies checked")


def run_audit(data_root, feature_tables=None):
    root = Path(data_root)
    specs = {
        "customers": "raw/customers.csv", "customer_360": "processed/customer_360.csv",
        "labels": "processed/product_takeup_labels.csv",
        "transaction_labels": "processed/transaction_category_labels.csv",
        "transactions": "raw/transactions.csv", "vehicles": "raw/vehicles.csv",
        "energy_usage": "raw/energy_usage.csv", "digital_usage": "raw/digital_usage.csv",
        "TRAIN": "splits/train_customers.csv", "VALIDATION": "splits/validation_customers.csv",
        "TEST": "splits/test_customers.csv",
    }
    tables, results, correlations = {}, [], []
    for name, rel in specs.items():
        if not (root / rel).is_file():
            results.append(_check("input:" + name, False, "Required input missing"))
        else:
            tables[name] = pd.read_csv(root / rel)
    if results:
        return results, correlations
    try:
        outputs = feature_tables if feature_tables is not None else {
            name: load_features(tables[name], table_name=name)
            for name in ("customer_360", "transactions")}
        if not {"customer_360", "transactions"} <= set(outputs):
            raise ValueError("Required feature outputs missing")
        results.extend(audit_feature_tables(outputs))
        results.append(audit_splits(tables["customers"], {k: tables[k] for k in ("TRAIN", "VALIDATION", "TEST")}))
        results.append(_check("customer_360_coverage", tables["customer_360"].customer_id.is_unique
                       and set(tables["customers"].customer_id) == set(tables["customer_360"].customer_id),
                       "Customer feature keys must cover raw customers"))
        results.extend(audit_dates(tables["customer_360"],
                                  {k: tables[k] for k in ("transactions", "vehicles", "energy_usage", "digital_usage")}))
        label_results, correlations = audit_labels(tables["labels"], tables["customer_360"], outputs["customer_360"])
        results.extend(label_results)
        results.append(audit_transaction_labels(tables["transactions"], tables["transaction_labels"], outputs["transactions"]))
    except (KeyError, ValueError, TypeError):
        results.append(_check("input_structure", False, "Invalid audit input/configuration; no payload logged"))
    return results, correlations


def write_report(results, correlations, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Leakage audit", "", "Diagnostics on synthetic data; PASS does not prove absence of leakage.",
             "", "| Check | Result | Detail |", "|---|---|---|"]
    lines += [f"| {r['check']} | {r['status']} | {r['detail']} |" for r in results]
    lines += ["", "## Label/numeric-feature correlations", "",
              "Absolute Pearson correlation above 0.9 fails. Undefined correlations are not evidence of independence.",
              "", "| Product | Label | Feature | Correlation | Observations |", "|---|---|---|---|---|"]
    lines += [f"| {r['product_code']} | {r['label']} | {r['feature']} | "
              f"{r['correlation'] if r['correlation'] is not None else 'UNDEFINED'} | {r['observations']} |"
              for r in correlations]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="data/doctored")
    parser.add_argument("--output", default="data/reports/rai/leakage.md")
    args = parser.parse_args()
    results, correlations = run_audit(args.data_root)
    write_report(results, correlations, args.output)
    failures = sum(r["status"] == "FAIL" for r in results)
    print(f"leakage: {len(results) - failures} PASS, {failures} FAIL")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
