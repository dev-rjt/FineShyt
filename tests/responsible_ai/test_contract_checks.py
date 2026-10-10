import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from responsible_ai.audit_log import append_audit
from responsible_ai.bias_audit import audit_bias, write_bias_report
from responsible_ai.canary_test import assert_no_canary
from responsible_ai.contract_checks import load_records, validate_customer_response, validate_record
from responsible_ai.scenario_tests import evaluate_scenarios, guard_cases

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def fixture(name="recommended_ev.json"):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "name",
    ["recommended_ev.json", "suppressed_ev.json", "insufficient_data_ev.json"],
)
def test_valid_api_examples(name):
    assert validate_record(fixture(name)) == []


def test_api_wrapper_loading(tmp_path):
    path = tmp_path / "response.json"
    path.write_text(json.dumps({"items": [fixture()], "data_as_of": "2026-06-30"}))
    assert load_records(path) == [fixture()]


@pytest.mark.parametrize(
    "field,value",
    [
        ("propensity", 1.01),
        ("confidence", -0.1),
        ("propensity", True),
        ("propensity", float("nan")),
        ("status", "ELIGIBLE"),
        ("product_id", "GP99"),
        ("opportunity", "GREEN_LOAN"),
        ("data_as_of", "30-06-2026"),
    ],
)
def test_invalid_top_level_fields(field, value):
    record = fixture()
    record[field] = value
    assert validate_record(record)


def test_unknown_missing_and_product_mapping():
    record = fixture()
    record["private_name"] = "PRIVATE NAME"
    errors = validate_record(record)
    assert errors and "PRIVATE NAME" not in str(errors)
    record = fixture()
    del record["confidence"]
    assert validate_record(record)
    record = fixture()
    record["product_id"] = "GP02"
    assert "inconsistent product mapping" in str(validate_record(record))


def test_gate_overrides_high_propensity_and_customer_visibility():
    record = fixture("suppressed_ev.json")
    assert record["propensity"] == 0.91
    assert not validate_record(record)
    assert validate_record(record, customer_visible=True)
    record["status"] = "RECOMMENDED"
    assert validate_record(record)


def test_impact_range_missingness_and_provenance():
    record = fixture()
    record["impact"]["metrics"][0]["low"] = 1300
    assert "unordered" in str(validate_record(record))
    record = fixture("insufficient_data_ev.json")
    record["impact"]["metrics"] = [{
        "metric": "CO2E_KG",
        "unit": "kg CO2e per year",
        "low": 0,
        "central": 0,
        "high": 0,
    }]
    assert validate_record(record)
    record = fixture()
    record["impact"]["factors"][0]["kg_co2e_per_unit"] = None
    assert "production provenance required" in str(validate_record(record))
    assert not validate_record(record, allow_stub_placeholders=True)


def test_llm_scope_verification_and_claims():
    before = fixture()
    before["insight"] = None
    after = fixture()
    assert not validate_record(after, before_llm=before)
    after["propensity"] = 0.99
    assert "LLM_WRITE_SCOPE" in str(validate_record(after, before_llm=before))
    record = fixture()
    record["insight"]["text"] = "You are pre-approved for this product."
    assert "prohibited eligibility" in str(validate_record(record))
    record = fixture()
    record["insight"]["verified"] = False
    assert validate_record(record)


def test_customer_response_helper():
    assert validate_customer_response([fixture()]) == []
    errors = validate_customer_response([fixture("suppressed_ev.json")])
    assert errors and errors[0][0] == 0


def test_append_log_allowlist_and_append_only(tmp_path):
    record = fixture()
    path = tmp_path / "audit.jsonl"
    append_audit(record, path)
    first = path.read_bytes()
    append_audit(record, path)
    assert path.read_bytes().startswith(first)
    entries = [json.loads(line) for line in path.read_text().splitlines()]
    assert set(entries[0]) == {
        "event_id",
        "customer_id",
        "product_id",
        "opportunity",
        "opportunity_status",
        "impact_status",
        "gate_pass",
        "insight_source",
        "model_version",
        "rule_version",
        "factor_ids",
        "data_as_of",
        "timestamp",
    }
    assert record["insight"]["text"] not in path.read_text()


def test_bias_counts_gaps_and_suppression(tmp_path):
    records = []
    for index in range(12):
        record = fixture()
        record["customer_id"] = f"C{index + 1:05d}"
        record["propensity"] = 0.2 if index < 10 else 0.8
        if index >= 5:
            record = fixture("suppressed_ev.json")
            record["customer_id"] = f"C{index + 1:05d}"
            record["propensity"] = 0.2 if index < 10 else 0.8
        records.append(record)
    customers = pd.DataFrame({
        "customer_id": [f"C{index + 1:05d}" for index in range(12)],
        "age_band": ["25-34"] * 10 + ["45-54"] * 2,
        "income_band": ["UNDER_20000"] * 6 + ["40000_59999"] * 6,
    })
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
    assert all(row["status"] == "PASS" for row in guard_cases())
    path = tmp_path / "demo_scenarios.csv"
    pd.DataFrame({"customer_id": ["C10001"], "scenario": ["ACTUAL_DATASET_NAME"]}).to_csv(path, index=False)
    result = evaluate_scenarios(path, [fixture()])
    assert result[-1]["case"] == "ACTUAL_DATASET_NAME" and result[-1]["status"] == "PASS"
    assert evaluate_scenarios(path, [])[-1]["status"] == "FAIL"


def test_canary_scan_detects_leaks(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text('{"message":"ZZ TESTNAME"}')
    with pytest.raises(AssertionError):
        assert_no_canary([tmp_path])
    path.write_text("{}")
    assert_no_canary([tmp_path])
