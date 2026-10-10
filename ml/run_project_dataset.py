"""Train and score the ML pipeline on the team's canonical data/ dataset."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import joblib
import pandas as pd

from config import MODEL_DIR, OUT_DIR, PRODUCTS
from contract import build_record, validate_record
from project_adapter import adapt_customer_360, wide_labels
from project_impact import canonical_impact
from propensity import train_all
from rules import eligibility, eligibility_detail
from txn_classifier import train_txn_classifier

def load_split(data_root: Path) -> pd.DataFrame:
    frames = []
    for filename, value in [("train_customers.csv", "train"), ("validation_customers.csv", "val"), ("test_customers.csv", "test")]:
        frame = pd.read_csv(data_root / "splits" / filename)
        frame["split"] = value
        frames.append(frame[["customer_id", "split"]])
    return pd.concat(frames, ignore_index=True)

def main(data_root: Path, train_transaction_model: bool = True):
    validation = json.loads((data_root / "reports" / "validation_report.json").read_text())
    if validation.get("overall_status") != "PASS":
        raise RuntimeError("Dataset validation_report.json is not PASS. Fix the dataset before model training.")

    source = pd.read_csv(data_root / "processed" / "customer_360.csv")
    features = adapt_customer_360(source, data_root / "raw" / "customer_products.csv")
    features.to_csv(data_root / "processed" / "ml_customer_360.csv", index=False)
    indexed = features.set_index("customer_id")
    rule_frame = eligibility(indexed)
    labels_long = pd.read_csv(data_root / "processed" / "product_takeup_labels.csv")
    labels = wide_labels(labels_long, rule_frame)
    split = load_split(data_root)

    txn_report = None
    if train_transaction_model:
        transactions = pd.read_csv(data_root / "raw" / "transactions.csv")
        txn_labels = pd.read_csv(data_root / "processed" / "transaction_category_labels.csv").rename(columns={"true_category": "category"})
        _, _, txn_report = train_txn_classifier(transactions, txn_labels, split, model_filename="project_txn_classifier.joblib")

    models, report = train_all(indexed, labels, rule_frame, split, artifact_prefix="project_",
                               model_filename="project_propensity_models.joblib", candidate_only=False)
    if txn_report:
        report["txn_categorisation"] = txn_report
    (OUT_DIR / "project_evaluation_report.json").write_text(json.dumps(report, indent=2, default=float))

    factors = pd.read_csv(data_root / "reference" / "emission_factors.csv")
    cutoff = json.loads((data_root / "dataset_config.json").read_text())["cutoff_date"]
    split_map = split.set_index("customer_id").split
    records, summary, request_number = [], [], 0
    for product in PRODUCTS:
        model = models[product]
        predictions = model.predict(indexed)
        reasons = model.reason_details(indexed)
        for (customer_id, row), reason_detail in zip(indexed.iterrows(), reasons):
            request_number += 1
            elig = eligibility_detail(row, product)
            impact = canonical_impact(product, row, elig, factors)
            record = build_record(customer_id, product, row, predictions.loc[customer_id], reason_detail,
                                  model.threshold, request_number, impact_section=impact, data_cutoff=cutoff)
            record["audit"]["split"] = split_map.loc[customer_id]
            record["audit"]["dataset_version"] = validation["dataset_version"]
            validate_record(record)
            records.append(record)
            summary.append({"customer_id": customer_id, "product_code": product,
                            "propensity": record["prediction"]["propensity"],
                            "confidence": record["prediction"]["confidence"],
                            "eligibility_status": record["eligibility"]["status"],
                            "decision": record["recommendation"]["decision"],
                            "priority_score": record["recommendation"]["priority_score"],
                            "impact_status": record["impact"]["status"],
                            "split": split_map.loc[customer_id]})

    output = OUT_DIR / "project_dataset"
    output.mkdir(exist_ok=True)
    with (output / "opportunities_all.jsonl").open("w") as stream:
        for record in records:
            stream.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
    with (output / "test_predictions.jsonl").open("w") as stream:
        for record in records:
            if record["audit"]["split"] == "test":
                stream.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
    summary_frame = pd.DataFrame(summary)
    summary_frame.to_csv(output / "recommendations_summary.csv", index=False)
    print("\nSUCCESS: trained on the team's validated dataset")
    print("Customers:", len(indexed), "| Opportunity records:", len(records))
    print("Models:", MODEL_DIR / "project_propensity_models.joblib")
    print("Outputs:", output)
    print("Recommended:", summary_frame[summary_frame.decision == "RECOMMEND"].groupby("product_code").size().to_dict())

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--skip-transaction-model", action="store_true", help="Skip transaction model retraining for a faster rerun")
    args = parser.parse_args()
    main(args.data_root, train_transaction_model=not args.skip_transaction_model)
