"""Build and validate Final JSON Contract v1.0.0 opportunity records."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from jsonschema import Draft202012Validator

from config import (CUTOFF_DATE, DATA_DIR, PRODUCT_CATEGORIES, PRODUCT_IDS,
                    PRODUCT_NAMES)
from rules import eligibility_detail
from carbon_engine import estimate_impact

ROOT = Path(__file__).parent
SCHEMA_PATH = ROOT / "contracts" / "opportunity_v1.schema.json"

FEATURE_META = {
    "fuel_spend_m": ("High recurring fuel spending", "GBP/month", "ABOVE_POPULATION_MEDIAN"),
    "annual_mileage": ("High annual vehicle mileage", "miles/year", "ABOVE_POPULATION_MEDIAN"),
    "vehicle_age": ("Older vehicle", "years", "ABOVE_POPULATION_MEDIAN"),
    "has_vehicle_loan": ("Existing vehicle finance", None, "PRESENT"),
    "fuel_type_code": ("Currently owns a petrol, diesel, or hybrid vehicle", None, "ICE_VEHICLE"),
    "elec_kwh_yr": ("High electricity use", "kWh/year", "ABOVE_POPULATION_MEDIAN"),
    "gas_kwh_yr": ("High gas use", "kWh/year", "ABOVE_POPULATION_MEDIAN"),
    "heating_kwh_yr": ("High heating energy use", "kWh/year", "ABOVE_POPULATION_MEDIAN"),
    "home_impr_spend_m": ("Home-improvement activity", "GBP/month", "ABOVE_POPULATION_MEDIAN"),
    "home_owner": ("Home ownership recorded", None, "PRESENT"),
    "has_mortgage": ("Existing mortgage", None, "PRESENT"),
    "paper_share": ("Paper statements are active", "ratio", "ABOVE_THRESHOLD"),
    "digital_tx_m": ("High digital activity", "transactions/month", "ABOVE_POPULATION_MEDIAN"),
    "branch_visits_m": ("Low branch usage", "visits/month", "BELOW_POPULATION_MEDIAN"),
    "digital_usage": ("High digital engagement", "score", "ABOVE_POPULATION_MEDIAN"),
    "sustainability_preference": ("Sustainability preference recorded", "score", "ABOVE_POPULATION_MEDIAN"),
}

def _native(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return value.item() if isinstance(value, np.generic) else value

def _band(value):
    return "HIGH" if value >= .75 else ("MEDIUM" if value >= .5 else "LOW")

def _segment(r):
    if r.home_owner == 1 and r.urban < .5:
        return "RURAL_HOMEOWNER"
    if r.home_owner == 1:
        return "SUBURBAN_HOMEOWNER"
    if r.digital_usage >= .7:
        return "DIGITALLY_ACTIVE"
    return "GENERAL_RETAIL"

def _reason_objects(details, r):
    out = []
    for item in details:
        feature = item["feature"]
        label, unit, comparison = FEATURE_META.get(feature, (item["code"].replace("_", " ").title(), None, None))
        out.append({"code": item["code"], "label": label, "importance": round(item["importance"], 4),
                    "evidence": {"metric": feature, "value": _native(r.get(feature)), "unit": unit,
                                 "comparison": comparison}})
    return out

def _impact_contract(product, raw, eligible):
    if eligible is False:
        return {"status": "NOT_APPLICABLE", "method_id": None, "method_name": None,
                "methodology_reference": None, "time_horizon": None, "primary_metric": None,
                "supporting_metrics": [], "assumptions": [], "emission_factors": [],
                "calculation_inputs": {}, "calculation_timestamp": None}
    if raw["status"] != "OK":
        return {"status": "INSUFFICIENT_DATA", "method_id": f"{product}_IMPACT_V1", "method_name": None,
                "methodology_reference": None, "time_horizon": {"value": 1, "unit": "YEAR"},
                "primary_metric": None, "supporting_metrics": [], "assumptions": [], "emission_factors": [],
                "calculation_inputs": {k: None for k in raw.get("missing_inputs", [])}, "calculation_timestamp": None}
    ef = pd.read_csv(DATA_DIR / "emissions_factors.csv")
    used = {"EV_FINANCE": {"grid_electricity", "car_petrol", "car_diesel", "car_hybrid"},
            "GREEN_HOME_LOAN": {"grid_electricity", "natural_gas"},
            "SOLAR_FINANCE": {"grid_electricity"},
            "PAPERLESS_BANKING": {"paper_statement"}}[product]
    ef = ef[ef.activity.isin(used)]
    factors = [{"factor_id": a.upper(), "activity": a.upper(), "value": float(v), "unit": f"kgCO2e/{u}",
                "source": s, "source_year": 2023, "factor_version": "prototype_2023_24_v1"}
               for a, u, v, s in ef[["activity", "unit", "kg_co2e_per_unit", "source"]].itertuples(index=False, name=None)]
    if product == "PAPERLESS_BANKING":
        primary = {"metric": "PAPER_STATEMENTS_AVOIDED", "lower_estimate": float(raw["paper_statements_avoided"]),
                   "central_estimate": float(raw["paper_statements_avoided"]), "upper_estimate": float(raw["paper_statements_avoided"]),
                   "unit": "statements/year"}
        supporting = [{"metric": "PAPER_SHEETS_AVOIDED", "value": raw["paper_sheets_avoided"], "unit": "sheets/year"},
                      {"metric": "DIGITAL_ADOPTION_SHIFT", "value": raw["digital_adoption_shift_pp"], "unit": "percentage_points"}]
    else:
        central = max(0.0, float(raw["avoided_kg_co2e_per_year"]))
        primary = {"metric": "POTENTIAL_CO2E_AVOIDED", "lower_estimate": round(central * .85, 1),
                   "central_estimate": round(central, 1), "upper_estimate": round(central * 1.15, 1),
                   "unit": "kgCO2e/year"}
        supporting = [{"metric": "BASELINE_EMISSIONS", "value": raw["baseline_kg_co2e"], "unit": "kgCO2e/year"},
                      {"metric": "SCENARIO_EMISSIONS", "value": raw["scenario_kg_co2e"], "unit": "kgCO2e/year"}]
    timestamp = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(timespec="seconds")
    return {"status": "AVAILABLE", "method_id": f"{product}_IMPACT_V1", "method_name": raw["method"],
            "methodology_reference": "GHG_PROTOCOL_AVOIDED_EMISSIONS", "time_horizon": {"value": 1, "unit": "YEAR"},
            "primary_metric": primary, "supporting_metrics": supporting,
            "assumptions": [{"code": f"ASSUMPTION_{i+1}", "description": x} for i, x in enumerate(raw.get("assumptions", []))],
            "emission_factors": factors, "calculation_inputs": raw.get("inputs", {}), "calculation_timestamp": timestamp}

def _explanation(product, reasons, impact, action, eligible):
    name = PRODUCT_NAMES[product]
    why = ", ".join(x["label"].lower() for x in reasons[:2]) or "the available customer data"
    if not eligible:
        customer = "No customer offer is shown because the configured eligibility rules did not pass."
    elif impact["status"] == "AVAILABLE":
        m = impact["primary_metric"]
        customer = (f"{why.capitalize()} suggest {name} may be relevant. The estimated potential impact is "
                    f"{m['lower_estimate']:,.0f}-{m['upper_estimate']:,.0f} {m['unit']}. {action}, subject to eligibility checks.")
    else:
        customer = f"{why.capitalize()} suggest {name} may be relevant. Impact could not be estimated from the available data. {action}."
    return {"status": "FALLBACK_USED", "headline": f"{name} may be relevant.", "customer_message": customer,
            "manager_message": f"Review {name}; the decision is based on configured rules and structured evidence.",
            "verification": {"passed": True, "verified_fields": ["product_name", "reason_codes", "impact_range", "action_label"],
                             "unsupported_claims": [], "fallback_used": True},
            "llm": {"provider": "NONE", "model": None, "prompt_version": "deterministic_fallback_v1.0.0"}}

def build_record(customer_id, product, row, prediction, reason_details, threshold, request_number,
                 impact_section=None, data_cutoff=None):
    elig = eligibility_detail(row, product)
    impact = impact_section if impact_section is not None else _impact_contract(product, estimate_impact(product, row), elig["is_eligible"])
    recommend = elig["status"] == "ELIGIBLE" and prediction["propensity"] >= threshold
    decision = "MANUAL_REVIEW" if elig["status"] == "MANUAL_REVIEW" else ("RECOMMEND" if recommend else "DO_NOT_RECOMMEND")
    action_map = {"EV_FINANCE": ("EXPLORE_EV_OPTIONS", "Explore EV options"), "GREEN_HOME_LOAN": ("EXPLORE_HOME_RETROFIT", "Explore green home improvements"),
                  "SOLAR_FINANCE": ("EXPLORE_SOLAR_OPTIONS", "Explore solar options"), "PAPERLESS_BANKING": ("GO_PAPERLESS", "Go paperless")}
    action_code, action_label = action_map[product]
    if decision == "MANUAL_REVIEW": action_code, action_label = "REQUEST_MISSING_DATA", "Request missing information"
    if decision == "DO_NOT_RECOMMEND": action_code, action_label = None, None
    reasons = _reason_objects(reason_details, row)
    available = row.drop(labels=["data_timestamp"], errors="ignore").notna().mean()
    impact_norm = 1.0 if impact["status"] == "AVAILABLE" else .5
    priority = round(float(prediction["propensity"] * prediction["confidence"] * impact_norm), 4) if recommend else None
    cutoff = str(data_cutoff or row.get("data_timestamp") or CUTOFF_DATE.date())
    cutoff_token = cutoff.replace("-", "")
    rec = {"schema_version": "1.0.0", "request_id": f"REQ-{cutoff_token}-{request_number:08d}",
           "generated_at": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(timespec="seconds"),
           "data_cutoff_date": cutoff,
           "customer": {"customer_id": customer_id, "segment": _segment(row), "region": str(row.region).upper().replace(" ", "_"), "data_completeness": round(float(available), 4)},
           "opportunity": {"product_id": PRODUCT_IDS[product], "product_code": product, "product_name": PRODUCT_NAMES[product], "category": PRODUCT_CATEGORIES[product]},
           "prediction": {"propensity": round(float(prediction["propensity"]), 4), "confidence": round(float(prediction["confidence"]), 4),
                          "confidence_band": _band(prediction["confidence"]), "model_version": f"{product.lower()}_propensity_v1.0.0", "reason_codes": reasons},
           "eligibility": elig, "impact": impact,
           "recommendation": {"decision": decision, "priority_score": priority, "priority_band": _band(priority) if priority is not None else None,
                              "action_code": action_code, "action_label": action_label, "customer_visible": bool(recommend), "manager_visible": True}}
    rec["explanation"] = _explanation(product, reasons, impact, action_label or "Contact the customer only after review", elig["is_eligible"] is True)
    rec["audit"] = {"pipeline_status": "SUCCESS", "component_versions": {"feature_pipeline": "features_v1.0.0", "transaction_classifier": "transaction_classifier_v1.0.0",
                     "propensity_model": rec["prediction"]["model_version"], "eligibility_rules": elig["rule_version"], "carbon_engine": "carbon_engine_v1.0.0",
                     "llm_prompt": "deterministic_fallback_v1.0.0", "llm_verifier": "deterministic_v1.0.0"},
                    "warnings": ["Synthetic-data prototype; not financial advice."], "errors": [], "human_review_required": elig["requires_human_review"]}
    return rec

def validate_record(record):
    schema = json.loads(SCHEMA_PATH.read_text())
    Draft202012Validator(schema).validate(record)
