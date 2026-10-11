"""Reshape pipeline outputs for the API contract without retraining any ML model.

run_pipeline.py writes engine-native impacts and POSITIVE_MODEL_SIGNAL_* evidence codes. This step rewrites
impact_json in the contract format and replaces evidence codes with reason codes from the fixed vocabulary.
Excluded rows keep their EXCLUDED:<code> marker; recommend flags are left exactly as the pipeline set them.
"""
from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd

from config import DATA_DIR, MODEL_DIR, OUT_DIR
from contract_adapter import contract_impact, contract_reasons


def rebuild() -> None:
    features = pd.read_csv(DATA_DIR / "customer_360.csv").set_index("customer_id")
    recommendations = pd.read_csv(OUT_DIR / "recommendations_all.csv")
    models = joblib.load(MODEL_DIR / "propensity_models.joblib")

    excluded = recommendations.reason_codes.fillna("").astype(str).str.startswith("EXCLUDED:")
    reasons = recommendations.reason_codes.fillna("").astype(str).copy()
    for product, model in models.items():
        mask = (recommendations.opportunity == product) & ~excluded
        rows = features.loc[recommendations.loc[mask, "customer_id"]]
        reasons.loc[mask] = [";".join(codes) for codes in contract_reasons(model, rows)]

    payloads, statuses, central_values = [], [], []
    for record, is_excluded in zip(recommendations.itertuples(index=False), excluded):
        if is_excluded or record.customer_id not in features.index:
            impact, status, central = {}, "NOT_APPLICABLE", np.nan
        else:
            impact = contract_impact(record.opportunity, features.loc[record.customer_id])
            status = impact["status"]
            central = impact.get("avoided_kg_co2e_per_year")
        payloads.append(json.dumps(impact))
        statuses.append(status)
        central_values.append(np.nan if central is None else central)

    recommendations["reason_codes"] = reasons
    recommendations["impact_status"] = statuses
    recommendations["est_avoided_kg_co2e_yr"] = central_values
    recommendations["impact_json"] = payloads
    recommendations.to_csv(OUT_DIR / "recommendations_all.csv", index=False)

    test = recommendations[recommendations.split == "test"]
    previous = OUT_DIR / "test_predictions.csv"
    if previous.exists():  # keep the pipeline's actual_takeup labels for evaluation
        labels = pd.read_csv(previous, usecols=lambda column: column in {"customer_id", "opportunity", "actual_takeup"})
        if "actual_takeup" in labels:
            test = test.merge(labels, on=["customer_id", "opportunity"], how="left")
    test.to_csv(previous, index=False)


if __name__ == "__main__":
    rebuild()
