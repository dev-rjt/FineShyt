"""Validate API opportunity objects without repairing or logging payload data."""

import argparse
import json
import math
import re
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "contracts/opportunity_v1.schema.json"
PRODUCT_OPPORTUNITIES = {
    "GP01": "EV_FINANCE",
    "GP02": "GREEN_HOME_LOAN",
    "GP03": "SOLAR_FINANCE",
    "GP04": "PAPERLESS_BANKING",
    "GP05": "GREEN_INVESTMENTS",
    "GP06": "GREEN_LOANS",
}
PROHIBITED_OUTCOME_CLAIMS = re.compile(
    r"\b(?:eligible|approved|pre-approved|qualif(?:y|ies|ied)|guaranteed)\b",
    re.IGNORECASE,
)


def load_records(path):
    """Load a record, record list, JSONL file, or API response with ``items``."""
    path = Path(path)
    if path.suffix == ".jsonl":
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            records = data["items"]
        else:
            records = data if isinstance(data, list) else [data]
    if not records or any(not isinstance(record, dict) for record in records):
        raise ValueError("Expected one or more API opportunity objects")
    return records


def _walk(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(item, (path + "." + key).strip("."))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}[{index}]")
    else:
        yield path, value


def _schema_violations(record, schema):
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    violations = []
    for error in validator.iter_errors(record):
        path = ".".join(str(part) for part in error.absolute_path) or "$"
        violations.append(f"{path}: schema {error.validator} violation")
    return violations


def validate_record(
    record,
    *,
    schema=None,
    before_llm=None,
    customer_visible=None,
    allow_stub_placeholders=False,
):
    """Return safe, value-free violations for one API Opportunity object.

    ``customer_visible=True`` applies the customer-endpoint suppression rule.
    ``before_llm`` proves that only ``insight`` changed during explanation.
    Stub mode accepts the app's explicit null provenance placeholders; strict
    mode is the production default and rejects them for an ``OK`` impact.
    """
    if not isinstance(record, dict):
        return ["$: record must be an object"]
    schema = schema if schema is not None else json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    violations = _schema_violations(record, schema)
    if violations:
        return sorted(set(violations))

    for path, value in _walk(record):
        if isinstance(value, str) and (not value.strip() or value.strip().upper() == "N/A"):
            violations.append(f"{path}: unavailable string must be null")
        if isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isfinite(value):
            violations.append(f"{path}: non-finite number")

    status = record["status"]
    gate = record["gate"]
    impact = record["impact"]
    insight = record["insight"]
    action = record["action"]
    failed_codes = {item["code"] for item in gate["failed_rules"]}
    reason_codes = {item["code"] for item in record["reason_codes"]}

    if PRODUCT_OPPORTUNITIES[record["product_id"]] != record["opportunity"]:
        violations.append("product_id/opportunity: inconsistent product mapping")
    if bool(gate["failed_rules"]) == gate["rule_pass"]:
        violations.append("gate: rule_pass and failed_rules are inconsistent")
    if not failed_codes <= reason_codes:
        violations.append("reason_codes: every failed gate rule must be represented")
    if "eligibility" not in gate["note"].lower():
        violations.append("gate.note: must state that authorised eligibility checks still apply")

    if status == "SUPPRESSED":
        if gate["rule_pass"] or not failed_codes:
            violations.append("status: suppressed opportunity requires a failed gate rule")
        if insight is not None or action is not None:
            violations.append("status: suppressed opportunity cannot have insight or action")
        if not record.get("suppression_reason") or record.get("suppression_reason") not in failed_codes:
            violations.append("suppression_reason: must name a failed gate rule")
        if record["rank_in_customer"] is not None or record["rank_score"] is not None:
            violations.append("ranking: suppressed opportunity cannot be ranked")
    else:
        if not gate["rule_pass"] or failed_codes:
            violations.append("status: visible candidate requires a passing product-rule gate")
        if insight is None or action is None:
            violations.append("status: non-suppressed opportunity requires insight and action")
        if record["rank_in_customer"] is None or record["rank_score"] is None:
            violations.append("ranking: non-suppressed opportunity requires rank fields")

    if customer_visible is True and status == "SUPPRESSED":
        violations.append("customer_visible: suppressed opportunities never reach customer endpoints")

    if status == "RECOMMENDED" and impact["status"] != "OK":
        violations.append("status: recommended opportunity requires an OK impact")
    if status == "INSUFFICIENT_DATA" and impact["status"] != "INSUFFICIENT_DATA":
        violations.append("status: insufficient-data opportunity requires insufficient-data impact")

    if impact["status"] == "OK":
        if not impact["metrics"] or impact["missing_inputs"]:
            violations.append("impact: OK requires metrics and no missing inputs")
        if not impact["assumptions"] or not impact["factors"]:
            violations.append("impact: OK requires documented assumptions and factors")
        for index, metric in enumerate(impact["metrics"]):
            if not metric["low"] <= metric["central"] <= metric["high"]:
                violations.append(f"impact.metrics[{index}]: estimate range is unordered")
        if not allow_stub_placeholders:
            for index, assumption in enumerate(impact["assumptions"]):
                if assumption["value"] is None or assumption["source"].lower() == "placeholder":
                    violations.append(f"impact.assumptions[{index}]: production provenance required")
            for index, factor in enumerate(impact["factors"]):
                if any(factor[key] is None for key in ("kg_co2e_per_unit", "unit", "source_year")):
                    violations.append(f"impact.factors[{index}]: production provenance required")
                if factor["source"].lower() == "placeholder":
                    violations.append(f"impact.factors[{index}]: production provenance required")
    elif impact["metrics"] or impact["assumptions"] or impact["factors"]:
        violations.append("impact: insufficient data cannot carry estimates or provenance")
    elif status != "SUPPRESSED" and not impact["missing_inputs"]:
        violations.append("impact.missing_inputs: required for an insufficient-data opportunity")

    if insight is not None:
        if insight["verified"] is not True:
            violations.append("insight.verified: customer text must be verified")
        if PROHIBITED_OUTCOME_CLAIMS.search(insight["text"]):
            violations.append("insight.text: prohibited eligibility or approval claim")
    if action is not None:
        if "eligibility" not in action["note"].lower():
            violations.append("action.note: must preserve the eligibility disclaimer")
        if PROHIBITED_OUTCOME_CLAIMS.search(action["label"]):
            violations.append("action.label: prohibited eligibility or approval claim")

    if before_llm is not None:
        before = {key: value for key, value in before_llm.items() if key != "insight"}
        after = {key: value for key, value in record.items() if key != "insight"}
        if before != after:
            violations.append("LLM_WRITE_SCOPE: only insight may change")
    return sorted(set(violations))


def validate_customer_response(records, *, allow_stub_placeholders=False):
    """Validate all opportunities returned by a customer-facing endpoint."""
    return [
        (index, errors)
        for index, record in enumerate(records)
        if (errors := validate_record(
            record,
            customer_visible=True,
            allow_stub_placeholders=allow_stub_placeholders,
        ))
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("records")
    parser.add_argument(
        "--customer-visible",
        action="store_true",
        help="Apply customer endpoint suppression rules",
    )
    parser.add_argument(
        "--allow-stub-placeholders",
        action="store_true",
        help="Allow explicit placeholder provenance from USE_STUBS=true",
    )
    args = parser.parse_args()
    records = load_records(args.records)
    failures = sum(
        bool(
            validate_record(
                record,
                customer_visible=args.customer_visible,
                allow_stub_placeholders=args.allow_stub_placeholders,
            )
        )
        for record in records
    )
    print(f"contract: {len(records) - failures} PASS, {failures} FAIL")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
