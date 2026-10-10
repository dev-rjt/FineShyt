"""JSON Schema and deterministic consistency checks; never repairs records."""
import argparse
import json
import math
import re
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_PATH = Path(__file__).with_name("opportunity_v1.schema.json")
COMPONENTS = {"feature_pipeline", "transaction_classifier", "propensity_model",
              "eligibility_rules", "carbon_engine", "llm_prompt", "llm_verifier"}


def load_records(path):
    path = Path(path)
    if path.suffix == ".jsonl":
        records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    else:
        data = json.loads(path.read_text())
        records = data if isinstance(data, list) else [data]
    if not records or any(not isinstance(record, dict) for record in records):
        raise ValueError("Expected nonempty JSON object records")
    return records


def _walk(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(item, (path + "." + key).strip("."))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _walk(item, f"{path}[{i}]")
    else:
        yield path, value


def validate_record(record, *, schema=None, before_llm=None):
    """Return violations without payload values. LLM scope needs a before snapshot.

    A single final record cannot prove who wrote it, whether text is supported,
    or whether zero was used to mean missing. Those limits are explicit.
    """
    violations = []
    if not isinstance(record, dict):
        return ["$: record must be an object"]
    schema = schema if schema is not None else json.loads(SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for error in validator.iter_errors(record):
        path = ".".join(str(part) for part in error.absolute_path) or "$"
        violations.append(f"{path}: schema {error.validator} violation")
    if violations:
        return sorted(set(violations))  # Do not traverse malformed nested types.
    version = record.get("schema_version")
    if not isinstance(version, str) or not re.fullmatch(r"1\.\d+\.\d+", version):
        violations.append("schema_version: incompatible or malformed version")
    for path, value in _walk(record):
        if isinstance(value, str) and (not value.strip() or value.strip().upper() == "N/A"):
            violations.append(f"{path}: unavailable string must be null")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not math.isfinite(value):
                violations.append(f"{path}: non-finite number")
            if value == -1:
                violations.append(f"{path}: prohibited missing-value sentinel")
        if path.endswith(("generated_at", "calculation_timestamp")) and value is not None:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.utcoffset() is None:
                    raise ValueError
            except (AttributeError, TypeError, ValueError):
                violations.append(f"{path}: timezone-aware timestamp required")
    if not isinstance(record.get("generated_at"), str):
        violations.append("generated_at: run timestamp required")
    sections = {name: record.get(name) for name in
                ("eligibility", "recommendation", "impact", "explanation", "audit", "prediction")}
    if any(not isinstance(value, dict) for value in sections.values()):
        return sorted(set(violations + ["$: required pipeline sections must be objects"]))
    elig, rec, impact, expl, audit, prediction = (sections[name] for name in sections)
    status = elig.get("status")
    allowed = status == "ELIGIBLE" and rec.get("decision") == "RECOMMEND"
    if rec.get("customer_visible") is True and not allowed:
        violations.append("recommendation.customer_visible: eligibility/decision gate failed")
    if status != "ELIGIBLE" and rec.get("decision") == "RECOMMEND":
        violations.append("recommendation.decision: propensity cannot override eligibility")
    expected_eligible = {"ELIGIBLE": True, "INELIGIBLE": False,
                         "MANUAL_REVIEW": None, "INSUFFICIENT_DATA": None}
    if status in expected_eligible and elig.get("is_eligible") is not expected_eligible[status]:
        violations.append("eligibility.is_eligible: inconsistent with status")
    if (status == "MANUAL_REVIEW" or rec.get("decision") == "MANUAL_REVIEW"
            or elig.get("requires_human_review") is True) and audit.get("human_review_required") is not True:
        violations.append("audit.human_review_required: manual review must be recorded")
    if status == "ELIGIBLE" and (elig.get("failed_rules") or elig.get("missing_requirements")):
        violations.append("eligibility: eligible decision has failed/missing requirements")
    if impact.get("status") != "AVAILABLE":
        primary = impact.get("primary_metric")
        if primary is not None:
            violations.append("impact.primary_metric: unavailable impact must be null or omitted")
        if impact.get("supporting_metrics"):
            violations.append("impact.supporting_metrics: unavailable impact cannot carry estimates")
    else:
        for key in ("method_id", "method_name", "methodology_reference", "calculation_timestamp"):
            if not isinstance(impact.get(key), str) or not impact[key].strip():
                violations.append(f"impact.{key}: available impact requires provenance")
        primary = impact.get("primary_metric") or {}
        estimates = [primary.get(k) for k in ("lower_estimate", "central_estimate", "upper_estimate")]
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool)
                   and math.isfinite(x) for x in estimates):
            violations.append("impact.primary_metric: available estimates must be finite numbers")
        elif not estimates[0] <= estimates[1] <= estimates[2]:
            violations.append("impact.primary_metric: estimate range is unordered")
        if not isinstance(primary.get("unit"), str) or not primary.get("unit"):
            violations.append("impact.primary_metric.unit: required")
        horizon = impact.get("time_horizon") or {}
        value = horizon.get("value")
        if (not isinstance(value, (int, float)) or isinstance(value, bool)
                or value <= 0 or not horizon.get("unit")):
            violations.append("impact.time_horizon: positive value and unit required")
        for key, required in (("assumptions", {"code", "description"}),
                              ("emission_factors", {"factor_id", "activity", "value", "unit",
                                                    "source", "source_year", "factor_version"})):
            items = impact.get(key)
            if not isinstance(items, list) or not items:
                violations.append(f"impact.{key}: documented provenance required")
            elif any(not isinstance(item, dict) or not required <= set(item)
                     or any(item.get(field) is None for field in required) for item in items):
                violations.append(f"impact.{key}: incomplete provenance")
    verification = expl.get("verification") or {}
    generated = any(expl.get(key) is not None for key in ("headline", "customer_message", "manager_message"))
    if generated and expl.get("status") not in {"VERIFIED", "FALLBACK_USED"}:
        violations.append("explanation: generated text must be verified or deterministic fallback")
    if expl.get("status") == "VERIFIED" and verification.get("passed") is not True:
        violations.append("explanation.verification.passed: verified explanation requires true")
    if verification.get("unsupported_claims") and not verification.get("fallback_used"):
        violations.append("explanation: unsupported claims require fallback")
    if expl.get("status") == "FALLBACK_USED" and verification.get("fallback_used") is not True:
        violations.append("explanation.verification.fallback_used: must be true")
    versions = audit.get("component_versions")
    if not isinstance(versions, dict) or not COMPONENTS <= set(versions) or any(
            not isinstance(versions.get(key), str) or not versions[key].strip() for key in COMPONENTS):
        violations.append("audit.component_versions: all component versions required")
    if audit.get("errors") and audit.get("pipeline_status") == "SUCCESS":
        violations.append("audit.pipeline_status: errors cannot accompany SUCCESS")
    if before_llm is not None:
        before = {k: v for k, v in before_llm.items() if k != "explanation"}
        after = {k: v for k, v in record.items() if k != "explanation"}
        if before != after:
            violations.append("LLM_WRITE_SCOPE: only explanation may change")
    return sorted(set(violations))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("records")
    args = parser.parse_args()
    records = load_records(args.records)
    failures = sum(bool(validate_record(record)) for record in records)
    print(f"contract: {len(records) - failures} PASS, {failures} FAIL")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
