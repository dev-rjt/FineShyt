"""Refresh deterministic impact payloads without retraining any ML model."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from carbon_engine import estimate_impact
from config import DATA_DIR, OUT_DIR


def rebuild() -> None:
    features = pd.read_csv(DATA_DIR / "customer_360.csv").set_index("customer_id")
    recommendations = pd.read_csv(OUT_DIR / "recommendations_all.csv")

    payloads, statuses, central_values = [], [], []
    for record in recommendations.itertuples(index=False):
        if str(record.reason_codes).startswith("EXCLUDED:") or record.customer_id not in features.index:
            impact = {}
            status, central = "NOT_APPLICABLE", np.nan
        else:
            impact = estimate_impact(record.opportunity, features.loc[record.customer_id])
            status = impact["status"]
            central = impact.get("avoided_kg_co2e_per_year", np.nan)
        payloads.append(json.dumps(impact))
        statuses.append(status)
        central_values.append(central)

    recommendations["impact_status"] = statuses
    recommendations["est_avoided_kg_co2e_yr"] = central_values
    recommendations["impact_json"] = payloads
    recommendations.to_csv(OUT_DIR / "recommendations_all.csv", index=False)
    recommendations[recommendations.split == "test"].to_csv(OUT_DIR / "test_predictions.csv", index=False)


if __name__ == "__main__":
    rebuild()
