"""Inference-only entry point used by a future API or dashboard."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import joblib
import pandas as pd

from config import MODEL_DIR, PRODUCTS
from contract import build_record, validate_record
from project_adapter import adapt_customer_360
from project_impact import canonical_impact
from rules import eligibility_detail

def predict(data_root: Path, customer_id: str | None = None):
    models = joblib.load(MODEL_DIR / "project_propensity_models.joblib")
    raw = pd.read_csv(data_root / "processed" / "customer_360.csv")
    if customer_id:
        raw = raw[raw.customer_id == customer_id]
        if raw.empty:
            raise ValueError(f"Unknown customer_id: {customer_id}")
    features = adapt_customer_360(raw, data_root / "raw" / "customer_products.csv").set_index("customer_id")
    factors = pd.read_csv(data_root / "reference" / "emission_factors.csv")
    cutoff = json.loads((data_root / "dataset_config.json").read_text())["cutoff_date"]
    records, request_number = [], 0
    for product in PRODUCTS:
        model = models[product]
        predictions = model.predict(features)
        reasons = model.reason_details(features)
        for (cid, row), reason_detail in zip(features.iterrows(), reasons):
            request_number += 1
            elig = eligibility_detail(row, product)
            impact = canonical_impact(product, row, elig, factors)
            record = build_record(cid, product, row, predictions.loc[cid], reason_detail, model.threshold,
                                  request_number, impact_section=impact, data_cutoff=cutoff)
            validate_record(record)
            records.append(record)
    return records

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--customer-id", help="Score one customer; omit to score all customers")
    parser.add_argument("--output", type=Path, default=Path("ml/outputs/project_dataset/inference.json"))
    args = parser.parse_args()
    result = predict(args.data_root, args.customer_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, default=str))
    print(f"Wrote {len(result)} opportunity records to {args.output}")
