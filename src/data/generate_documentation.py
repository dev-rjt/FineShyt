"""Generate the data dictionary and file inventory from built artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


DESCRIPTIONS = {
    "customer_id": "Synthetic stable customer identifier.",
    "transaction_id": "Unique transaction identifier.",
    "transaction_date": "Transaction posting date; never later than the feature cutoff.",
    "merchant_description": "Raw-like merchant text used for transaction categorisation.",
    "true_category": "Gold transaction category label from the fixed eight-class vocabulary.",
    "source_basis": "Whether the row is fully synthetic or seeded from a public source.",
    "take_up": "Binary label showing adoption inside the post-cutoff outcome window.",
    "take_up_date": "Synthetic adoption date for positive labels; blank for negative labels.",
    "data_cutoff_date": "Last date allowed in model features.",
    "product_code": "Fixed product identifier from the four required opportunities.",
    "annual_mileage": "Estimated annual miles; may be missing by design.",
    "electricity_kwh": "Monthly household electricity consumption in kWh.",
    "gas_kwh": "Monthly household gas consumption in kWh.",
    "data_completeness": "Fraction of vehicle, energy and digital data domains available.",
    "factor_value": "Official 2026 UK conversion factor value.",
    "factor_unit": "Output unit for the emissions factor.",
    "activity_unit": "Unit required by the emissions factor input.",
}


def infer_description(column: str) -> str:
    if column in DESCRIPTIONS:
        return DESCRIPTIONS[column]
    text = column.replace("_", " ")
    if column.startswith("has_"):
        return f"Boolean indicator for {text[4:]}."
    if column.endswith("_spend_6m"):
        return f"Total {text[:-9]} spending in the six months before cutoff, GBP."
    if column.startswith("average_"):
        return f"Customer-level average of {text[8:]}."
    if column.endswith("_id"):
        return f"Identifier for {text[:-3]}."
    return text.capitalize() + "."


def main() -> None:
    root = Path("data")
    files = sorted(
        p for p in root.rglob("*.csv")
        if "external/cache" not in p.as_posix()
    )
    dictionary_rows = []
    inventory_rows = []
    for path in files:
        frame = pd.read_csv(path, nrows=250)
        full_rows = sum(1 for _ in path.open(encoding="utf-8")) - 1
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        inventory_rows.append({
            "file": path.as_posix(), "rows": full_rows, "columns": len(frame.columns),
            "size_bytes": path.stat().st_size, "sha256": sha,
        })
        for column in frame.columns:
            series = frame[column]
            examples = [str(x)[:60] for x in series.dropna().unique()[:3]]
            dictionary_rows.append({
                "file": path.as_posix(), "column": column, "inferred_type": str(series.dtype),
                "nullable_in_sample": bool(series.isna().any()),
                "description": infer_description(column), "example_values": " | ".join(examples),
            })
    dictionary = pd.DataFrame(dictionary_rows)
    inventory = pd.DataFrame(inventory_rows)
    dictionary.to_csv(root / "data_dictionary.csv", index=False)
    inventory.to_csv(root / "file_inventory.csv", index=False)
    summary = {
        "file_count": len(inventory), "dictionary_column_count": len(dictionary),
        "total_rows_across_csv_files": int(inventory["rows"].sum()),
        "total_csv_bytes": int(inventory["size_bytes"].sum()),
    }
    (root / "reports/documentation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
