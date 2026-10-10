from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from carbon_engine.schemas import EligibilityResult, EligibilityStatus, ProductId, RuleDecision, RuleOutcome
from eligibility.dsl import condition_uses_fields, eval_condition
from eligibility.interventions import select_green_home_intervention

ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = ROOT / "config" / "rules_v1.yaml"
THRESHOLDS_PATH = ROOT / "config" / "thresholds.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _canonicalize_customer_fields(customer_ctx: dict[str, Any]) -> dict[str, Any]:
    ctx = dict(customer_ctx)

    alias_map = {
        "account_status": "has_current_account",
        "green_offers_opt_out": "green_offers_opt_out",
        "vulnerability_flag": "vulnerability_flag",
        "has_arrears": "has_arrears",
        "affordability_prescreen": "affordability_prescreen",
        "held_products": "held_products",
        "vehicle_fuel_type": "vehicle_fuel_type",
        "annual_distance": "annual_mileage",
        "annual_distance_unit": "annual_distance_unit",
        "annual_distance_source": "annual_distance_source",
        "annual_fuel_spend_gbp": "fuel_spend_6m",
        "electricity_kwh_monthly": "electricity_kwh_monthly",
        "gas_kwh_monthly": "gas_kwh_monthly",
        "months_electricity_data": "energy_data_months",
        "months_gas_data": "energy_data_months",
        "paper_statements": "paper_statements_active",
        "digital_logins_90d": "average_mobile_logins_3m",
        "requires_paper_comms": "requires_paper_comms",
        "home_ownership": "home_owner",
        "property_type": "property_type",
        "has_solar": "has_solar",
        "cutoff_date": "data_cutoff_date",
    }
    for old_key, new_key in alias_map.items():
        if old_key in ctx and new_key not in ctx:
            ctx[new_key] = ctx[old_key]

    if "account_status" in ctx and "has_current_account" not in ctx:
        status = ctx["account_status"]
        ctx["has_current_account"] = 1 if str(status).upper() == "ACTIVE" else 0
    elif "has_current_account" in ctx and "account_status" not in ctx:
        ctx["account_status"] = "ACTIVE" if int(ctx["has_current_account"]) == 1 else "INACTIVE"

    if "home_ownership" in ctx and "home_owner" not in ctx:
        ctx["home_owner"] = bool(ctx["home_ownership"] in {"OWNER_OUTRIGHT", "MORTGAGE"})
    elif "home_owner" in ctx and "home_ownership" not in ctx:
        ctx["home_ownership"] = "OWNER_OUTRIGHT" if bool(ctx["home_owner"]) else "RENTER"

    if "paper_statements" in ctx and "paper_statements_active" not in ctx:
        ctx["paper_statements_active"] = 1.0 if bool(ctx["paper_statements"]) else 0.0
    elif "paper_statements_active" in ctx and "paper_statements" not in ctx:
        ctx["paper_statements"] = bool(float(ctx["paper_statements_active"]) > 0)

    if "digital_logins_90d" in ctx and "average_mobile_logins_3m" not in ctx:
        ctx["average_mobile_logins_3m"] = float(ctx["digital_logins_90d"])
    elif "average_mobile_logins_3m" in ctx and "digital_logins_90d" not in ctx:
        ctx["digital_logins_90d"] = float(ctx["average_mobile_logins_3m"])

    if "cutoff_date" in ctx and "data_cutoff_date" not in ctx:
        ctx["data_cutoff_date"] = ctx["cutoff_date"]
    elif "data_cutoff_date" in ctx and "cutoff_date" not in ctx:
        ctx["cutoff_date"] = ctx["data_cutoff_date"]

    if "average_monthly_electricity_kwh" in ctx and "electricity_kwh_monthly" not in ctx:
        val = float(ctx["average_monthly_electricity_kwh"])
        ctx["electricity_kwh_monthly"] = [val] * 12
    if "average_monthly_gas_kwh" in ctx and "gas_kwh_monthly" not in ctx:
        val = float(ctx["average_monthly_gas_kwh"])
        ctx["gas_kwh_monthly"] = [val] * 12

    if "energy_data_months" in ctx and "months_electricity_data" not in ctx:
        ctx["months_electricity_data"] = ctx["energy_data_months"]
    if "energy_data_months" in ctx and "months_gas_data" not in ctx:
        ctx["months_gas_data"] = ctx["energy_data_months"]

    if "has_existing_ev" not in ctx and ctx.get("vehicle_fuel_type") == "BEV":
        ctx["has_existing_ev"] = True
    elif "has_existing_ev" not in ctx and ctx.get("vehicle_fuel_type") in {"HYBRID", "PHEV"}:
        ctx["has_existing_ev"] = False

    return ctx


def _enrich_context(
    customer_ctx: dict[str, Any],
    product: str,
    thresholds: dict[str, Any],
    run_date: date,
) -> dict[str, Any]:
    ctx = _canonicalize_customer_fields(customer_ctx)
    ctx["_eval_product"] = product

    cutoff = ctx.get("cutoff_date")
    if isinstance(cutoff, str):
        cutoff = date.fromisoformat(cutoff)
    if cutoff is not None:
        stale_days = (run_date - cutoff).days
        ctx["_data_stale"] = stale_days > int(thresholds.get("data_max_age_days", 90))
    else:
        ctx["_data_stale"] = True

    held = ctx.get("held_products") or []
    ctx["_holds_target_product"] = product in held

    me = int(ctx.get("months_electricity_data") or 0)
    mg = int(ctx.get("months_gas_data") or 0)
    min_gh = int(thresholds.get("min_months_energy_green_home", 12))
    ctx["_insufficient_energy_history_gh"] = not (me >= min_gh or mg >= min_gh)

    min_solar = int(thresholds.get("min_months_electricity_solar", 6))
    ctx["_insufficient_electricity_solar"] = me < min_solar

    elec = ctx.get("electricity_kwh_monthly") or []
    vals = [v for v in elec if v is not None]
    annual_elec = sum(float(v) for v in vals) if len(vals) >= 12 else (
        (sum(float(v) for v in vals) / len(vals) * 12) if len(vals) >= 6 else 0
    )
    min_kwh = float(thresholds.get("min_electricity_kwh_year_solar", 1500))
    ctx["_annual_electricity_kwh"] = annual_elec
    ctx["_low_electricity_solar"] = annual_elec < min_kwh if len(vals) >= 6 else False

    intervention = select_green_home_intervention(ctx)
    ctx["_no_green_home_intervention"] = intervention is None

    return ctx


def _aggregate_status(decisions: list[RuleDecision], conditions: list[str]) -> EligibilityStatus:
    has_hard_fail = any(
        d.outcome == RuleOutcome.FAIL and d.severity == "HARD_BLOCK" for d in decisions
    )
    if has_hard_fail:
        return EligibilityStatus.NOT_ELIGIBLE

    has_missing = any(d.outcome == RuleOutcome.MISSING for d in decisions)
    has_requires_data_fail = any(
        d.outcome == RuleOutcome.FAIL and d.severity == "REQUIRES_DATA" for d in decisions
    )
    if has_missing or has_requires_data_fail:
        return EligibilityStatus.INSUFFICIENT_DATA

    if conditions:
        return EligibilityStatus.ELIGIBLE_WITH_CONDITIONS
    return EligibilityStatus.ELIGIBLE


def evaluate_eligibility(
    customer_ctx: dict[str, Any],
    product: ProductId | str,
    *,
    run_date: Optional[date] = None,
    rules_path: Path = RULES_PATH,
    thresholds_path: Path = THRESHOLDS_PATH,
) -> EligibilityResult:
    if isinstance(product, ProductId):
        product = product.value
    else:
        product = str(product)
    rules_doc = _load_yaml(rules_path)
    thresholds = _load_yaml(thresholds_path)
    rule_version = thresholds.get("rule_version", rules_doc.get("version", "rules_v1.0.0"))
    run_date = run_date or date.today()

    ctx = _enrich_context(customer_ctx, product, thresholds, run_date)
    decisions: list[RuleDecision] = []
    conditions: list[str] = []
    no_auto_message = False

    for rule in rules_doc.get("rules", []):
        if product not in rule.get("products", []):
            continue

        missing: set[str] = set()
        when = rule.get("when_fails_if")
        condition_true = eval_condition(when, ctx, thresholds, missing)

        severity = rule.get("severity", "HARD_BLOCK")
        on_missing = rule.get("on_missing", "MISSING")

        fields_in_when = condition_uses_fields(when)
        missing_fields = {
            f
            for f in fields_in_when
            if not f.startswith("_") and ctx.get(f) is None
        }

        outcome: RuleOutcome
        code: str

        if missing_fields and on_missing == "MISSING":
            outcome = RuleOutcome.MISSING
            code = rule.get("fail_code", "EL_MISSING_DATA")
        elif condition_true and severity == "CONDITION":
            outcome = RuleOutcome.CONDITION
            code = rule.get("fail_code", rule.get("pass_code", "EL_COND"))
            text = rule.get("condition_text")
            if text and text not in conditions:
                conditions.append(text)
            if rule.get("id") == "G06":
                no_auto_message = True
        elif condition_true:
            outcome = RuleOutcome.FAIL
            code = rule.get("fail_code", "EL_FAIL")
        else:
            outcome = RuleOutcome.PASS
            code = rule.get("pass_code", "EL_PASS")

        evidence: dict[str, Any] = {}
        for f in condition_uses_fields(when):
            if f.startswith("_"):
                if f == "_data_stale":
                    evidence["cutoff_date"] = ctx.get("cutoff_date")
                    evidence["run_date"] = run_date.isoformat()
                elif f == "_holds_target_product":
                    evidence["held_products"] = ctx.get("held_products")
                continue
            val = ctx.get(f)
            if val is not None:
                evidence[f] = val

        decisions.append(
            RuleDecision(
                rule_id=rule["id"],
                outcome=outcome,
                code=code,
                severity=severity,
                criteria_source=rule.get("criteria_source"),
                evidence=evidence,
                rule_version=rule_version,
                condition_text=rule.get("condition_text") if outcome == RuleOutcome.CONDITION else None,
            )
        )

    status = _aggregate_status(decisions, conditions)

    return EligibilityResult(
        customer_id=str(customer_ctx.get("customer_id", "UNKNOWN")),
        product=ProductId(product),
        eligibility_status=status,
        conditions=conditions,
        decisions=decisions,
        evaluated_at=datetime.now(timezone.utc),
        rule_version=rule_version,
        no_automated_customer_message=no_auto_message,
    )
