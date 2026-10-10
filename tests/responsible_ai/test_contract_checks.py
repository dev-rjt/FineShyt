import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from responsible_ai.audit_log import append_audit
from responsible_ai.bias_audit import audit_bias, write_bias_report
from responsible_ai.canary_test import assert_no_canary
from responsible_ai.contract_checks import validate_record
from responsible_ai.scenario_tests import evaluate_scenarios, guard_cases

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def eligible():
    return json.loads((FIXTURES / "eligible_ev.json").read_text())


def completed(name):
    record = eligible()
    record.update(json.loads((FIXTURES / name).read_text()))
    if record["eligibility"]["status"] != "ELIGIBLE":
        record["explanation"] = json.loads((FIXTURES / "calculation_error.json").read_text())["explanation"]
    if record["eligibility"]["status"] == "MANUAL_REVIEW":
        record["audit"]["human_review_required"] = True
        record["explanation"] = json.loads((FIXTURES / "calculation_error.json").read_text())["explanation"]
    return record


@pytest.mark.parametrize("name", ["eligible_ev.json", "ineligible_ev.json", "missing_data_ev.json",
                                  "calculation_error.json", "conflicting_signals.json"])
def test_valid_examples(name):
    assert validate_record(completed(name)) == []


def test_partial_pdf_examples_are_not_full_records():
    for name in ["ineligible_ev.json", "missing_data_ev.json"]:
        assert validate_record(json.loads((FIXTURES / name).read_text()))


@pytest.mark.parametrize("section,field,value", [
    ("prediction", "propensity", 1.01), ("prediction", "confidence", -0.1),
    ("prediction", "propensity", True), ("prediction", "propensity", float("nan")),
    ("customer", "data_completeness", -1), ("recommendation", "priority_score", 2),
    ("eligibility", "status", "eligible"), ("opportunity", "product_code", "GREEN_LOAN"),
    ("recommendation", "decision", "recommend"), ("prediction", "confidence_band", "VERY_HIGH"),
    ("impact", "status", "MISSING"), ("explanation", "status", "GENERATED"),
    ("audit", "pipeline_status", "OK"),
])
def test_invalid_fields(section, field, value):
    record = eligible()
    record[section][field] = value
    assert validate_record(record)


def test_major_version_unknown_fields_and_missing_fields():
    record = eligible()
    record["schema_version"] = "2.0.0"
    assert validate_record(record)
    record = eligible()
    record["name"] = "PRIVATE NAME"
    errors = validate_record(record)
    assert errors and "PRIVATE NAME" not in str(errors)
    record = eligible()
    del record["prediction"]["confidence"]
    assert validate_record(record)


def test_visibility_and_propensity_never_eligibility():
    record = completed("ineligible_ev.json")
    assert record["prediction"]["propensity"] == 0.91
    record["recommendation"]["customer_visible"] = True
    assert validate_record(record)
    record["recommendation"]["customer_visible"] = False
    record["recommendation"]["decision"] = "RECOMMEND"
    assert validate_record(record)


@pytest.mark.parametrize("field", ["unit", "lower_estimate", "central_estimate", "upper_estimate"])
def test_available_impact_requires_values(field):
    record = eligible()
    record["impact"]["primary_metric"][field] = None
    assert validate_record(record)


def test_null_impact_unchanged_and_zero_valid_only_when_available():
    record = completed("missing_data_ev.json")
    before = copy.deepcopy(record)
    assert not validate_record(record) and record == before
    record["impact"]["primary_metric"] = eligible()["impact"]["primary_metric"]
    record["impact"]["primary_metric"]["central_estimate"] = 0
    assert validate_record(record)
    record = eligible()
    for key in ["lower_estimate", "central_estimate", "upper_estimate"]:
        record["impact"]["primary_metric"][key] = 0
    assert not validate_record(record)


@pytest.mark.parametrize("field", ["method_id", "time_horizon", "assumptions", "emission_factors"])
def test_provenance_required(field):
    record = eligible()
    del record["impact"][field]
    assert validate_record(record)


def test_llm_scope_and_verification():
    before = eligible()
    after = copy.deepcopy(before)
    after["explanation"]["headline"] = "Illustrative changed explanation"
    assert not validate_record(after, before_llm=before)
    after["prediction"]["propensity"] = 0.99
    assert "LLM_WRITE_SCOPE" in str(validate_record(after, before_llm=before))
    record = eligible()
    record["explanation"]["verification"]["passed"] = False
    assert validate_record(record)


def test_timestamp_sentinels_and_bad_shapes_do_not_crash():
    for value in ["2026-10-10T12:00:00", "N/A", ""]:
        record = eligible()
        record["generated_at"] = value
        assert validate_record(record)
    for value in [None, [], 1, "invalid"]:
        record = eligible()
        record["impact"]["primary_metric"] = value
        assert validate_record(record)


def test_append_log_allowlist_and_append_only(tmp_path):
    record = eligible()
    path = tmp_path / "audit.jsonl"
    append_audit(record, path)
    first = path.read_bytes()
    append_audit(record, path)
    assert path.read_bytes().startswith(first)
    entries = [json.loads(line) for line in path.read_text().splitlines()]
    assert set(entries[0]) == {"request_id", "customer_id", "product_code", "component_versions",
                               "factor_version", "statuses", "timestamp"}
    assert record["explanation"]["customer_message"] not in path.read_text()


def test_bias_counts_gaps_and_suppression(tmp_path):
    records = []
    for i in range(12):
        record = eligible()
        record["customer"]["customer_id"] = f"C{i + 1:05d}"
        record["prediction"]["propensity"] = 0.2 if i < 10 else 0.8
        if i >= 5:
            record["recommendation"]["decision"] = "DO_NOT_RECOMMEND"
            record["recommendation"]["customer_visible"] = False
        records.append(record)
    customers = pd.DataFrame({"customer_id": [f"C{i + 1:05d}" for i in range(12)],
                              "age_band": ["25-34"] * 10 + ["45-54"] * 2,
                              "income_band": ["UNDER_20000"] * 6 + ["40000_59999"] * 6})
    report, gaps = audit_bias(records, customers)
    small = report[report.suppressed]
    assert small.group_size.isna().all() and small.recommendation_rate.isna().all()
    big = report[~report.suppressed].iloc[0]
    assert big.recommendation_rate == 0.5
    report, gaps = audit_bias(records, customers, minimum_group_size=2)
    age_gap = gaps[gaps.dimension.eq("age_band")].iloc[0]
    assert age_gap.recommendation_rate_gap == 0.5
    assert age_gap.mean_propensity_gap == pytest.approx(0.6)
    write_bias_report(report, gaps, tmp_path / "bias.csv", tmp_path / "bias.md", 2)
    assert "does not establish fairness" in (tmp_path / "bias.md").read_text()
    with pytest.raises(ValueError):
        audit_bias(records[:-1], customers)


def test_scenarios_read_actual_names_and_guard_cases(tmp_path):
    assert all(r["status"] == "PASS" for r in guard_cases())
    path = tmp_path / "demo_scenarios.csv"
    pd.DataFrame({"customer_id": ["C10001"], "scenario": ["ACTUAL_DATASET_NAME"]}).to_csv(path, index=False)
    result = evaluate_scenarios(path, [eligible()])
    assert result[-1]["case"] == "ACTUAL_DATASET_NAME" and result[-1]["status"] == "PASS"
    assert evaluate_scenarios(path, [])[ -1]["status"] == "FAIL"


def test_canary_scan_detects_leaks(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text('{"message":"ZZ TESTNAME"}')
    with pytest.raises(AssertionError):
        assert_no_canary([tmp_path])
    path.write_text('{}')
    assert_no_canary([tmp_path])
