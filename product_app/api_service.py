"""Data and live-scoring service used by the FastAPI backend.

The dashboard never predicts or calculates sustainability impact. This module
is the integration boundary that invokes the trained propensity models, product
rules, deterministic impact engine, and structured explanation payload.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import joblib
import numpy as np
import pandas as pd

from carbon_engine import estimate_impact
from config import CUTOFF_DATE, DATABASE_PATH, MODEL_DIR, OUT_DIR, PRODUCTS, PRODUCT_IDS, REPOSITORY_ROOT
from insight_layer import ACTION, EXCLUSION_TEXT, PRODUCT_NAME, REASON_TEXT, build_payload, explain
from rules import eligibility
from txn_classifier import rule_classify


EXTERNAL_PRODUCT_CODE = {
    "EV_FINANCE": "EV_FINANCE",
    "GREEN_HOME": "GREEN_HOME_LOAN",
    "SOLAR_FINANCE": "SOLAR_FINANCE",
    "PAPERLESS": "PAPERLESS_BANKING",
}
INTERNAL_PRODUCT_CODE = {value: key for key, value in EXTERNAL_PRODUCT_CODE.items()}
RULE_VERSION = "product_gate_v1.0.0"
MODEL_VERSION = "lightgbm_ensemble_v1.0.0"
# Per-call LLM cap for API responses. Calls run in parallel, so a response waits at most about this
# long for wording, well inside the dashboard's 60 second request timeout; on timeout the template is used.
API_LLM_TIMEOUT_SECONDS = 20.0


def _records(frame: pd.DataFrame) -> list[dict]:
    clean = frame.astype(object).where(pd.notna(frame), None)
    return clean.to_dict(orient="records")


def ensure_database() -> Path:
    """Create the local database when a fresh checkout starts for the first time."""
    if not DATABASE_PATH.exists():
        subprocess.run(
            [sys.executable, str(REPOSITORY_ROOT / "db" / "build_demo_db.py"), "--quiet"],
            check=True,
        )
    return DATABASE_PATH


def connection() -> sqlite3.Connection:
    database = ensure_database()
    handle = sqlite3.connect(database)
    handle.execute("PRAGMA foreign_keys = ON")
    return handle


@lru_cache(maxsize=1)
def repository() -> dict:
    with connection() as database:
        recommendations = pd.read_sql_query("SELECT * FROM recommendations", database)
        recommendations["recommend"] = recommendations["recommend"].astype(bool)
        customers = pd.read_sql_query("SELECT * FROM customers", database)
        digital_usage = pd.read_sql_query("SELECT * FROM digital_usage", database)
        energy_usage = pd.read_sql_query("SELECT * FROM energy_usage", database)
        emission_factors = pd.read_sql_query("SELECT * FROM emission_factors", database)
        products = pd.read_sql_query(
            "SELECT product_id, product_name AS product, category, eligibility, sustainability_metric FROM green_products",
            database,
        )
    return {
        "recommendations": recommendations,
        "customers": customers,
        "digital_usage": digital_usage,
        "energy_usage": energy_usage,
        "emission_factors": emission_factors,
        "products": products,
        "evaluation": json.loads((OUT_DIR / "evaluation_report.json").read_text(encoding="utf-8")),
    }


@lru_cache(maxsize=1)
def scoring_assets() -> tuple[pd.DataFrame, dict]:
    with connection() as database:
        features = pd.read_sql_query("SELECT * FROM customer_features", database).set_index("customer_id")
    models = joblib.load(MODEL_DIR / "propensity_models.joblib")
    return features, models


@lru_cache(maxsize=1)
def data_catalog() -> dict:
    """Return safe database metadata for the bank-only architecture screen."""
    with connection() as database:
        objects = database.execute(
            "SELECT name, type FROM sqlite_master "
            "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        tables = []
        for name, object_type in objects:
            columns = [
                {"position": row[0] + 1, "column": row[1], "type": row[2], "nullable": not bool(row[3]), "primary_key": bool(row[5])}
                for row in database.execute(f'PRAGMA table_info("{name}")').fetchall()
            ]
            foreign_keys = [
                {"column": row[3], "references_table": row[2], "references_column": row[4]}
                for row in database.execute(f'PRAGMA foreign_key_list("{name}")').fetchall()
            ]
            row_count = database.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            tables.append({"name": name, "kind": object_type, "rows": row_count, "columns": columns, "foreign_keys": foreign_keys})
        metadata = database.execute(
            "SELECT schema_version, created_at, dataset_name, customer_count FROM schema_metadata LIMIT 1"
        ).fetchone()
    return {
        "engine": "SQLite 3",
        "database_file": DATABASE_PATH.name,
        "schema_version": metadata[0],
        "built_at": metadata[1],
        "dataset_name": metadata[2],
        "customer_count": metadata[3],
        "tables": tables,
    }


def customer_profile(customer_id: str) -> dict | None:
    row = repository()["customers"]
    match = row[row.customer_id == customer_id]
    return _records(match)[0] if len(match) else None


def product_catalog() -> list[dict]:
    products = repository()["products"]
    rows = []
    for row in _records(products):
        internal = next(product for product, product_id in PRODUCT_IDS.items() if product_id == row["product_id"])
        rows.append({
            "product_id": row["product_id"], "product": row["product"],
            "opportunity": EXTERNAL_PRODUCT_CODE[internal], "category": row["category"], "required": True,
            "intended_use_case": row["eligibility"],
            "eligibility": "Product-rule screen only; final eligibility uses authorised bank processes",
            "sustainability_metric": row["sustainability_metric"], "action_label": ACTION[internal],
        })
    return rows


def reason_catalog() -> list[dict]:
    rows = []
    for code, plain in REASON_TEXT.items():
        item = _reason(code)
        item["product_id"] = None
        rows.append(item)
    for code, plain in EXCLUSION_TEXT.items():
        item = _reason(code, "GATE")
        item["product_id"] = None
        rows.append(item)
    return rows


def customer_transactions(customer_id: str) -> list[dict]:
    with connection() as database:
        frame = pd.read_sql_query(
            "SELECT transaction_id, transaction_date AS txn_date, merchant_description, amount, debit_credit "
            "FROM bank_transactions WHERE customer_id = ? ORDER BY transaction_date DESC, transaction_id",
            database, params=(customer_id,),
        )
    frame["category"] = frame.merchant_description.map(rule_classify).str.upper().str.replace(" ", "_")
    frame["category_method"] = "RULE"
    frame["category_confidence"] = 1.0
    return _records(frame)


def customer_directory() -> list[dict]:
    customers = repository()["customers"]
    recommendations = repository()["recommendations"]
    visible = recommendations[recommendations.recommend].copy()
    visible["rank_score"] = visible.propensity * visible.confidence
    top = visible.sort_values(["customer_id", "rank_score"], ascending=[True, False]).drop_duplicates("customer_id")
    top = top[["customer_id", "opportunity", "rank_score"]].rename(columns={"opportunity": "top_opportunity", "rank_score": "top_rank_score"})
    frame = customers.merge(top, on="customer_id", how="left")
    frame["top_opportunity"] = frame["top_opportunity"].map(EXTERNAL_PRODUCT_CODE).fillna(frame["top_opportunity"])
    return _records(frame[["customer_id", "age", "income_band", "region", "home_owner", "top_opportunity", "top_rank_score"]])


def system_meta() -> dict:
    recs = repository()["recommendations"]
    customer_splits = recs[["customer_id", "split"]].drop_duplicates()
    splits = customer_splits.split.value_counts().to_dict()
    return {
        "cutoff_date": str(CUTOFF_DATE.date()), "takeup_window_days": 90,
        "customers": int(repository()["customers"].shape[0]),
        "splits": {"train": int(splits.get("train", 0)), "validation": int(splits.get("val", 0)), "test": int(splits.get("test", 0))},
        "generator_version": "synthetic-v1", "model_versions": {"categoriser": "tfidf-logreg-v1", "propensity": MODEL_VERSION},
        "generated_at": f"{CUTOFF_DATE.date()}T00:00:00Z",
    }


def business_summary() -> dict:
    rows = repository()["recommendations"]
    by_product = []
    totals = {metric: [0.0, 0.0, 0.0] for metric in ["CO2E_KG", "ENERGY_KWH", "PAPER_SHEETS", "DIGITAL_ADOPTION_PP"]}
    for product in PRODUCTS:
        group = rows[rows.opportunity == product]
        excluded = group.reason_codes.fillna("").str.startswith("EXCLUDED:")
        recommended = group.recommend & ~excluded
        by_product.append({
            "product_id": PRODUCT_IDS[product], "opportunity": EXTERNAL_PRODUCT_CODE[product],
            "recommended": int(recommended.sum()), "suppressed": int(excluded.sum()),
            "insufficient_data": int((group.impact_status == "INSUFFICIENT_DATA").sum()),
            "avg_propensity": round(float(group.propensity.mean()), 4),
        })
    recommended_rows = rows[rows.recommend & ~rows.reason_codes.fillna("").str.startswith("EXCLUDED:")].copy()
    recommended_rows["priority"] = recommended_rows.propensity * recommended_rows.confidence
    for _, customer_rows in recommended_rows.groupby("customer_id"):
        home = customer_rows[customer_rows.opportunity.isin(["GREEN_HOME", "SOLAR_FINANCE"])]
        if len(home) > 1:
            customer_rows = customer_rows.drop(home.sort_values("priority", ascending=False).index[1:])
        for payload in customer_rows.impact_json:
            impact = json.loads(payload)
            for metric in impact.get("metrics", []):
                bucket = totals[metric["metric"]]
                bucket[0] += metric["low"]; bucket[1] += metric["central"]; bucket[2] += metric["high"]
    def measure(metric: str) -> dict:
        low, central, high = totals[metric]
        return {"low": round(low, 2), "central": round(central, 2), "high": round(high, 2), "is_estimate": True}
    return {
        "customers_analysed": int(rows.customer_id.nunique()), "opportunities_by_product": by_product,
        "potential_impact": {
            "co2e_kg_per_year": measure("CO2E_KG"), "energy_kwh_per_year": measure("ENERGY_KWH"),
            "paper_sheets_per_year": measure("PAPER_SHEETS"), "digital_adoption_pp": measure("DIGITAL_ADOPTION_PP"),
        },
    }


def customer_360(customer_id: str) -> dict | None:
    profile = customer_profile(customer_id)
    if profile is None:
        return None
    features, _ = scoring_assets()
    if customer_id not in features.index:
        return None
    feature = features.loc[customer_id]
    with connection() as database:
        holdings = pd.read_sql_query(
            "SELECT product, start_date, balance, status FROM customer_products WHERE customer_id = ? ORDER BY start_date",
            database, params=(customer_id,),
        )
        vehicle = pd.read_sql_query(
            "SELECT vehicle_type, fuel_type, vehicle_age, annual_mileage FROM vehicles WHERE customer_id = ?",
            database, params=(customer_id,),
        )
    selected_features = {
        "fuel_spend_12m": round(float(feature.fuel_spend_m) * 12, 2),
        "annual_mileage": None if pd.isna(feature.annual_mileage) else float(feature.annual_mileage),
        "electricity_kwh_12m": None if pd.isna(feature.elec_kwh_yr) else float(feature.elec_kwh_yr),
        "paper_statement_ratio": None if pd.isna(feature.paper_share) else float(feature.paper_share),
    }
    missing = [name for name, value in selected_features.items() if value is None]
    completeness = round(1 - len(missing) / len(selected_features), 2)
    return {
        "customer_id": customer_id,
        "profile": profile,
        "features": selected_features,
        "holdings": _records(holdings),
        "vehicle": _records(vehicle)[0] if len(vehicle) else None,
        "data_quality": {"completeness": completeness, "missing_fields": missing},
        "data_as_of": str(feature.data_timestamp),
    }


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
            model = models[product]
            prediction = model.predict(row).iloc[0]
            model_reasons = model.reason_codes(row)[0]
            propensity = round(float(prediction.propensity), 4)
            confidence = round(float(prediction.confidence), 4)
            if allowed:
                reasons = model_reasons
                impact = estimate_impact(product, row.iloc[0])
                recommended = bool(propensity >= model.threshold)
                impact_status = impact["status"]
                estimated = impact.get("avoided_kg_co2e_per_year")
            else:
                reason = str(gates.loc[customer_id, f"exclusion_{product}"])
                reasons = [f"EXCLUDED:{reason}", *model_reasons]
                impact = {}
                estimated = None
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


@lru_cache(maxsize=1)
def impact_percentiles() -> dict[str, float]:
    rows = repository()["recommendations"]
    values: dict[str, list[float]] = {product: [] for product in PRODUCTS}
    for record in rows.itertuples(index=False):
        if str(record.reason_codes).startswith("EXCLUDED:"):
            continue
        try:
            impact = json.loads(record.impact_json)
            central = impact.get("estimate_central", impact.get("avoided_kg_co2e_per_year"))
            if central is not None:
                values[record.opportunity].append(float(central))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return {product: float(np.percentile(product_values, 90)) if product_values else 1.0
            for product, product_values in values.items()}


def _reason(code: str, kind: str = "DRIVER") -> dict:
    plain = REASON_TEXT.get(code) or EXCLUSION_TEXT.get(code) or code.replace("_", " ").lower()
    return {"code": code, "kind": kind, "label": code.replace("_", " ").title(), "plain_text": plain.capitalize()}


def _attach_insights(pending: list[tuple[dict, dict]]) -> None:
    """Explain recommended items in parallel; explain() never raises and falls back to the template."""
    if not pending:
        return
    with ThreadPoolExecutor(max_workers=min(4, len(pending))) as pool:
        results = list(pool.map(lambda pair: explain(pair[1], use_llm=True, timeout=API_LLM_TIMEOUT_SECONDS), pending))
    for (item, _), (text, explanation_source) in zip(pending, results):
        item["insight"] = {"text": text, "source": "LLM" if explanation_source == "llm" else "TEMPLATE", "verified": True}


def _canonicalise(records: list[dict], source: str, include_suppressed: bool) -> tuple[list[dict], str]:
    percentiles = impact_percentiles()
    result = []
    pending = []
    for record in records:
        internal = record["opportunity"]
        raw_codes = [code for code in str(record.get("reason_codes") or "").split(";") if code]
        excluded = bool(raw_codes and raw_codes[0].startswith("EXCLUDED:"))
        exclusion = raw_codes[0].split(":", 1)[1] if excluded else None
        impact = json.loads(record.get("impact_json") or "{}")
        recommended = bool(record.get("recommend")) and not excluded
        insufficient = not excluded and impact.get("status") == "INSUFFICIENT_DATA"
        status = "RECOMMENDED" if recommended else ("INSUFFICIENT_DATA" if insufficient else "SUPPRESSED")
        codes = raw_codes[1:] if excluded else raw_codes
        reasons = [_reason(code[5:], "DATA_QUALITY") if code.startswith("DATA:") else _reason(code) for code in codes]
        if exclusion:
            reasons.append(_reason(exclusion, "GATE"))
        canonical_impact = impact if impact else {
            "status": "INSUFFICIENT_DATA", "is_estimate": True, "horizon_months": 12,
            "method": "Not applicable because the product gate did not pass", "metrics": [],
            "assumptions": [], "factors": [], "missing_inputs": [],
        }
        if canonical_impact.get("status") == "OK":
            canonical_impact = {key: canonical_impact[key] for key in
                                ["status", "is_estimate", "horizon_months", "method", "metrics", "assumptions", "factors", "missing_inputs"]}
        central = None
        if impact.get("metrics"):
            central = impact["metrics"][0]["central"]
        propensity = record.get("propensity")
        confidence = record.get("confidence")
        score = None
        if status != "SUPPRESSED" and propensity is not None and confidence is not None:
            impact_index = min(float(central or 0) / max(percentiles.get(internal, 1), 1e-9), 1.0)
            score = round(float(propensity) * float(confidence) * impact_index, 4)
        gate = {
            "rule_pass": not excluded,
            "failed_rules": [] if not exclusion else [{"code": exclusion, "message": EXCLUSION_TEXT.get(exclusion, exclusion.replace("_", " ").title())}],
            "rule_version": RULE_VERSION,
            "note": "Product-rule screen only; subject to the institution's authorised eligibility checks",
        }
        item = {
            "customer_id": str(record["customer_id"]),
            "opportunity": EXTERNAL_PRODUCT_CODE[internal],
            "product_id": record["product_id"],
            "status": status,
            "propensity": None if propensity is None else float(propensity),
            "confidence": None if confidence is None else float(confidence),
            "reason_codes": reasons,
            "gate": gate,
            "impact": canonical_impact,
            "insight": None,
            "action": None,
            "suppression_reason": exclusion or ("BELOW_RECOMMENDATION_THRESHOLD" if status == "SUPPRESSED" else None),
            "rank_in_customer": None,
            "rank_score": score,
            "data_as_of": str(record["data_timestamp"]),
            "model_version": MODEL_VERSION,
        }
        if recommended:
            pending.append((item, build_payload(record)))
            item["action"] = {"label": ACTION[internal], "note": "Subject to eligibility checks"}
        result.append(item)
    _attach_insights(pending)
    visible = [item for item in result if item["status"] != "SUPPRESSED"]
    visible.sort(key=lambda item: item["rank_score"] or 0, reverse=True)
    for rank, item in enumerate(visible, 1):
        item["rank_in_customer"] = rank
    return (result if include_suppressed else visible), source


def canonical_opportunities(customer_id: str, include_suppressed: bool = False) -> tuple[list[dict], str]:
    records, source = score_customer(customer_id)
    return _canonicalise(records, source, include_suppressed)


def score_snapshot(snapshot: dict) -> dict:
    """Score an unpersisted scenario without borrowing values from another customer."""
    customer_id = str(snapshot.get("customer_id") or "SCENARIO")
    template, models = scoring_assets()
    row = pd.DataFrame(np.nan, index=[customer_id], columns=template.columns)
    row.index.name = "customer_id"
    profile = snapshot.get("profile") or {}
    vehicle = snapshot.get("vehicle") or {}
    holdings = snapshot.get("holdings") or []
    transactions = snapshot.get("transactions") or []
    energy = snapshot.get("energy_usage") or []
    digital = snapshot.get("digital_usage") or []

    explicit = {
        "age": profile.get("age"), "home_owner": None if profile.get("home_owner") is None else int(bool(profile.get("home_owner"))),
        "digital_usage": profile.get("digital_usage"), "sustainability_preference": profile.get("sustainability_preference"),
        "vehicle_age": vehicle.get("vehicle_age"), "annual_mileage": vehicle.get("annual_mileage"),
    }
    income = {"LOW": 0, "MID": 2, "HIGH": 4, "<20K": 0, "20-35K": 1, "35-50K": 2, "50-80K": 3, "80K+": 4}
    explicit["income_idx"] = income.get(str(profile.get("income_band", "")).upper())
    fuel = {"PETROL": 0, "DIESEL": 1, "HYBRID": 2, "ELECTRIC": 3, "EV": 3}
    explicit["fuel_type_code"] = fuel.get(str(vehicle.get("fuel_type", "")).upper())
    explicit["has_vehicle"] = int(bool(vehicle))
    for key, value in explicit.items():
        if key in row and value is not None:
            row.loc[customer_id, key] = value

    holding_names = [str(item.get("product", "")).upper() for item in holdings]
    for product_id in ["GP01", "GP02", "GP03", "GP04"]:
        row.loc[customer_id, f"holds_{product_id}"] = int(product_id in holding_names)
    row.loc[customer_id, "has_mortgage"] = int(any("MORTGAGE" in name for name in holding_names))
    row.loc[customer_id, "has_vehicle_loan"] = int(any("VEHICLE" in name for name in holding_names))
    row.loc[customer_id, "has_isa"] = int(any("ISA" in name for name in holding_names))
    row.loc[customer_id, "has_savings"] = int(any("SAVING" in name for name in holding_names))
    row.loc[customer_id, "has_credit_card"] = int(any("CREDIT" in name for name in holding_names))
    row.loc[customer_id, "has_personal_loan"] = int(any("PERSONAL" in name for name in holding_names))
    row.loc[customer_id, "n_products"] = len(holdings)
    row.loc[customer_id, "total_balance"] = sum(float(item.get("balance") or 0) for item in holdings)

    if energy:
        row.loc[customer_id, "elec_kwh_yr"] = sum(float(item.get("electricity_kwh") or 0) for item in energy)
        row.loc[customer_id, "gas_kwh_yr"] = sum(float(item.get("gas_kwh") or 0) for item in energy)
        row.loc[customer_id, "heating_kwh_yr"] = row.loc[customer_id, "gas_kwh_yr"]
    if digital:
        paper = sum(float(item.get("paper_statements") or 0) for item in digital)
        digital_statements = sum(float(item.get("digital_statements") or 0) for item in digital)
        total_statements = paper + digital_statements
        row.loc[customer_id, "paper_stmts_yr"] = paper
        row.loc[customer_id, "paper_share"] = paper / total_statements if total_statements else 0
        row.loc[customer_id, "digital_tx_m"] = np.mean([float(item.get("digital_transactions") or 0) for item in digital])
        row.loc[customer_id, "branch_visits_m"] = np.mean([float(item.get("branch_visits") or 0) for item in digital])
    if transactions:
        months = max(1, len({str(item.get("txn_date", ""))[:7] for item in transactions}))
        categories = [rule_classify(str(item.get("merchant_description", ""))) for item in transactions]
        amounts = [float(item.get("amount") or 0) for item in transactions]
        for category in ["Fuel", "Electricity", "Gas", "Public Transport", "Home Improvement", "Automotive", "Utilities", "Other"]:
            field = "spend_" + category.lower().replace(" ", "_") + "_m"
            row.loc[customer_id, field] = sum(amount for amount, value in zip(amounts, categories) if value == category) / months
        row.loc[customer_id, "fuel_spend_m"] = row.loc[customer_id, "spend_fuel_m"]
        row.loc[customer_id, "home_impr_spend_m"] = row.loc[customer_id, "spend_home_improvement_m"]
        row.loc[customer_id, "total_spend_m"] = sum(amounts) / months
        row.loc[customer_id, "n_fuel_txn"] = sum(value == "Fuel" for value in categories)
        row.loc[customer_id, "fuel_share_of_spend"] = sum(amount for amount, value in zip(amounts, categories) if value == "Fuel") / max(sum(amounts), 1)
        row.loc[customer_id, "txn_cat_mean_conf"] = 1.0
    row["data_timestamp"] = str(CUTOFF_DATE.date())

    gates = eligibility(row)
    records = []
    for product in PRODUCTS:
        model = models[product]
        prediction = model.predict(row).iloc[0]
        allowed = bool(gates.loc[customer_id, f"eligible_{product}"])
        reasons = model.reason_codes(row)[0]
        impact = estimate_impact(product, row.iloc[0]) if allowed else {}
        if impact.get("status") == "INSUFFICIENT_DATA":
            mapping = {"annual_mileage": "MISSING_MILEAGE", "fuel_type_code": "MISSING_FUEL_DATA"}
            reasons += [f"DATA:{mapping.get(field, 'LOW_DATA_COMPLETENESS')}" for field in impact["missing_inputs"]]
        if not allowed:
            reasons = [f"EXCLUDED:{gates.loc[customer_id, f'exclusion_{product}']}", *reasons]
        propensity, confidence = float(prediction.propensity), float(prediction.confidence)
        records.append({
            "customer_id": customer_id, "opportunity": product, "product_id": PRODUCT_IDS[product],
            "propensity": round(propensity, 4), "confidence": round(confidence, 4),
            "recommend": bool(allowed and impact.get("status") == "OK" and propensity >= model.threshold),
            "reason_codes": ";".join(reasons), "data_timestamp": str(CUTOFF_DATE.date()), "split": "scenario",
            "impact_status": impact.get("status", "NOT_APPLICABLE"),
            "est_avoided_kg_co2e_yr": impact.get("avoided_kg_co2e_per_year"), "impact_json": json.dumps(impact),
        })
    items, _ = _canonicalise(records, "ad_hoc_model", include_suppressed=True)
    important = ["age", "home_owner", "annual_mileage", "fuel_type_code", "elec_kwh_yr", "gas_kwh_yr", "paper_share"]
    missing = [field for field in important if pd.isna(row.loc[customer_id, field])]
    return {"customer_id": customer_id, "items": items,
            "data_quality": {"completeness": round(1 - len(missing) / len(important), 2), "missing_fields": missing},
            "data_as_of": str(CUTOFF_DATE.date()), "scoring_source": "ad_hoc_model"}


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
    database_file = ensure_database()
    model_file = MODEL_DIR / "propensity_models.joblib"
    return {
        "status": "ok",
        "customers": int(len(data["customers"])),
        "opportunity_records": int(len(data["recommendations"])),
        "live_scoring_ready": database_file.exists() and model_file.exists(),
        "components": {
            "frontend": "streamlit",
            "backend": "fastapi",
            "database": "sqlite_normalized_schema",
            "ml": "lightgbm_ensemble",
            "rules": "product_gate_v1",
            "impact": "deterministic_carbon_engine",
            "explanations": "grounded_template_with_optional_llm",
        },
    }
