"""End-to-end reproducible training and contract-compliant inference pipeline."""
import argparse
import json
import pandas as pd
from config import DATA_DIR, OUT_DIR, PRODUCTS
from contract import build_record, validate_record
from data_generation import make_all
from features import build_customer_360
from propensity import make_splits, train_all
from rules import eligibility
from txn_classifier import train_txn_classifier

def main(n_customers=5000):
    data = make_all(n=n_customers)
    split = make_splits(data["customers"], data["labels"])
    vec, clf, txn_report = train_txn_classifier(data["transactions"], data["txn_labels"], split)
    features = build_customer_360(data, vec, clf)
    features.to_csv(DATA_DIR / "customer_360.csv", index=False)
    indexed = features.set_index("customer_id")
    rule_frame = eligibility(indexed)
    models, report = train_all(indexed, data["labels"], rule_frame, split)
    report["txn_categorisation"] = txn_report
    (OUT_DIR / "evaluation_report.json").write_text(json.dumps(report, indent=2, default=float))

    split_map = split.set_index("customer_id").split
    records, flat_rows = [], []
    request_number = 0
    for product in PRODUCTS:
        model = models[product]
        predictions = model.predict(indexed)
        details = model.reason_details(indexed)
        for (customer_id, row), reason_detail in zip(indexed.iterrows(), details):
            request_number += 1
            record = build_record(customer_id, product, row, predictions.loc[customer_id], reason_detail,
                                  model.threshold, request_number)
            validate_record(record)
            record["audit"]["split"] = split_map.loc[customer_id]
            records.append(record)
            flat_rows.append({"customer_id": customer_id, "product_code": product,
                              "propensity": record["prediction"]["propensity"], "confidence": record["prediction"]["confidence"],
                              "eligibility_status": record["eligibility"]["status"], "decision": record["recommendation"]["decision"],
                              "customer_visible": record["recommendation"]["customer_visible"],
                              "impact_status": record["impact"]["status"], "split": split_map.loc[customer_id]})

    with (OUT_DIR / "opportunities_all.jsonl").open("w") as stream:
        for record in records:
            stream.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
    with (OUT_DIR / "test_predictions.jsonl").open("w") as stream:
        for record in records:
            if split_map.loc[record["customer"]["customer_id"]] == "test":
                stream.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
    summary = pd.DataFrame(flat_rows)
    summary.to_csv(OUT_DIR / "recommendations_summary.csv", index=False)
    print("\nValidated contract records:", len(records))
    print("Saved: opportunities_all.jsonl, test_predictions.jsonl, recommendations_summary.csv, evaluation_report.json")
    print("Recommended counts:", summary[summary.decision == "RECOMMEND"].groupby("product_code").size().to_dict())
    return data, features, models, records

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--customers", type=int, default=5000, help="Synthetic customer count (default: 5000)")
    args = parser.parse_args()
    main(args.customers)
