"""Data and live-scoring service used by the FastAPI backend.

The dashboard never predicts or calculates sustainability impact. This module
is the integration boundary that invokes the trained propensity models, product
rules, deterministic impact engine, and structured explanation payload.
"""
from __future__ import annotations

from functools import lru_cache
import json

import joblib
import numpy as np
import pandas as pd

from carbon_engine import estimate_impact
from config import DATA_DIR, MODEL_DIR, OUT_DIR, PRODUCTS, PRODUCT_IDS
from rules import eligibility


def _records(frame: pd.DataFrame) -> list[dict]:
    clean = frame.astype(object).where(pd.notna(frame), None)
    return clean.to_dict(orient="records")


@lru_cache(maxsize=1)
def repository() -> dict:
    recommendations = pd.read_csv(OUT_DIR / "recommendations_all.csv")
    customers = pd.read_csv(DATA_DIR / "customers.csv")
    return {
        "recommendations": recommendations,
        "customers": customers,
        "digital_usage": pd.read_csv(DATA_DIR / "digital_usage.csv"),
        "energy_usage": pd.read_csv(DATA_DIR / "energy_usage.csv"),
        "emission_factors": pd.read_csv(DATA_DIR / "emissions_factors.csv"),
        "products": pd.read_csv(DATA_DIR / "green_products.csv"),
        "evaluation": json.loads((OUT_DIR / "evaluation_report.json").read_text(encoding="utf-8")),
    }


@lru_cache(maxsize=1)
def scoring_assets() -> tuple[pd.DataFrame, dict]:
    features = pd.read_csv(DATA_DIR / "customer_360.csv").set_index("customer_id")
    models = joblib.load(MODEL_DIR / "propensity_models.joblib")
    return features, models


def customer_profile(customer_id: str) -> dict | None:
    row = repository()["customers"]
    match = row[row.customer_id == customer_id]
    return _records(match)[0] if len(match) else None


def precomputed_customer(customer_id: str) -> list[dict]:
    frame = repository()["recommendations"]
    return _records(frame[frame.customer_id == customer_id])


def score_customer(customer_id: str) -> tuple[list[dict], str]:
    """Run saved models + rules + impact engine for one customer.

    The checked-in precomputed result remains a safe fallback if an artifact is
    absent or incompatible, keeping the demo available without hiding the
    scoring source from callers.
    """
    try:
        features, models = scoring_assets()
        if customer_id not in features.index:
            return [], "not_found"
        row = features.loc[[customer_id]]
        gates = eligibility(row)
        split_rows = repository()["recommendations"]
        split_match = split_rows[split_rows.customer_id == customer_id]
        split = str(split_match.iloc[0].split) if len(split_match) else "unknown"
        records = []
        for product in PRODUCTS:
            allowed = bool(gates.loc[customer_id, f"eligible_{product}"])
            if allowed:
                model = models[product]
                prediction = model.predict(row).iloc[0]
                reasons = model.reason_codes(row)[0]
                impact = estimate_impact(product, row.iloc[0])
                propensity = round(float(prediction.propensity), 4)
                confidence = round(float(prediction.confidence), 4)
                recommended = bool(propensity >= model.threshold)
                impact_status = impact["status"]
                estimated = impact.get("avoided_kg_co2e_per_year")
            else:
                reason = str(gates.loc[customer_id, f"exclusion_{product}"])
                reasons = [f"EXCLUDED:{reason}"]
                impact = {}
                propensity = confidence = estimated = None
                recommended = False
                impact_status = "NOT_APPLICABLE"
            records.append({
                "customer_id": customer_id,
                "opportunity": product,
                "product_id": PRODUCT_IDS[product],
                "propensity": propensity,
                "confidence": confidence,
                "recommend": recommended,
                "reason_codes": ";".join(reasons),
                "data_timestamp": str(row.iloc[0].data_timestamp),
                "split": split,
                "impact_status": impact_status,
                "est_avoided_kg_co2e_yr": estimated,
                "impact_json": json.dumps(impact),
            })
        return records, "live_model"
    except Exception:
        fallback = precomputed_customer(customer_id)
        return fallback, "precomputed_fallback"


def bank_bootstrap() -> dict:
    data = repository()
    return {
        "recommendations": _records(data["recommendations"]),
        "customers": _records(data["customers"]),
        "digital_usage": _records(data["digital_usage"]),
        "energy_usage": _records(data["energy_usage"]),
        "emission_factors": _records(data["emission_factors"]),
        "products": _records(data["products"]),
        "evaluation": data["evaluation"],
    }


def feature_weights(product: str) -> list[dict]:
    if product not in PRODUCTS:
        raise KeyError(product)
    frame = pd.read_csv(OUT_DIR / f"feature_weights_{product}.csv")
    frame.columns = ["feature", "normalised_gain"]
    return _records(frame)


def health_details() -> dict:
    data = repository()
    feature_file = DATA_DIR / "customer_360.csv"
    model_file = MODEL_DIR / "propensity_models.joblib"
    return {
        "status": "ok",
        "customers": int(len(data["customers"])),
        "opportunity_records": int(len(data["recommendations"])),
        "live_scoring_ready": feature_file.exists() and model_file.exists(),
        "components": {
            "frontend": "streamlit",
            "backend": "fastapi",
            "ml": "lightgbm_ensemble",
            "rules": "product_gate_v1",
            "impact": "deterministic_carbon_engine",
            "explanations": "grounded_template_with_optional_llm",
        },
    }
