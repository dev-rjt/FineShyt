"""Record-based API scenarios; no eligibility rules or impact calculations."""

import argparse
import copy
import json
from pathlib import Path

import pandas as pd

from responsible_ai.contract_checks import load_records, validate_record

FIXTURES = Path(__file__).resolve().parents[1] / "tests/fixtures"


def _result(name, ok, detail):
    return {"case": name, "status": "PASS" if ok else "FAIL", "detail": detail}


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def guard_cases():
    """Mutate API fixtures to exercise invariant failures, not product rules."""
    recommended = _fixture("recommended_ev.json")
    suppressed = _fixture("suppressed_ev.json")
    missing = _fixture("insufficient_data_ev.json")
    results = [
        _result("RECOMMENDED_VALID", not validate_record(recommended), "Valid recommendation accepted"),
        _result("HIGH_PROPENSITY_SUPPRESSED", not validate_record(suppressed), "Failed gate overrides propensity"),
        _result("INSUFFICIENT_DATA", not validate_record(missing), "Missing inputs carry no estimates"),
    ]

    unsafe = copy.deepcopy(suppressed)
    results.append(_result(
        "SUPPRESSED_CUSTOMER_VISIBILITY_BLOCK",
        bool(validate_record(unsafe, customer_visible=True)),
        "Suppressed opportunity rejected from customer endpoints",
    ))
    unsafe = copy.deepcopy(recommended)
    unsafe["gate"]["rule_pass"] = False
    results.append(_result(
        "PROPENSITY_CANNOT_OVERRIDE_GATE",
        bool(validate_record(unsafe)),
        "Recommendation with failed gate rejected",
    ))
    unsafe = copy.deepcopy(missing)
    unsafe["impact"]["metrics"] = [{
        "metric": "CO2E_KG",
        "unit": "kg CO2e per year",
        "low": 0,
        "central": 0,
        "high": 0,
    }]
    results.append(_result(
        "MISSING_DATA_ZERO_REJECTED",
        bool(validate_record(unsafe)),
        "Missing impact cannot be represented as zero",
    ))
    return results


def evaluate_scenarios(scenario_path, records, *, expectations=None):
    scenarios = pd.read_csv(scenario_path)
    if list(scenarios.columns) != ["customer_id", "scenario"] or scenarios.isna().any().any():
        raise ValueError("Invalid demo_scenarios structure")
    results = guard_cases()
    for _, row in scenarios.iterrows():
        matches = [record for record in records if record.get("customer_id") == row.customer_id]
        valid = bool(matches) and all(not validate_record(record) for record in matches)
        detail = "Records exist and satisfy API safety invariants; scenario meaning not asserted"
        expected = (expectations or {}).get(row.scenario)
        if expected:
            product_id = expected["product_id"]
            matches = [record for record in matches if record.get("product_id") == product_id]
            valid &= bool(matches)
            for record in matches:
                for path, value in expected["fields"].items():
                    current = record
                    for field in path.split("."):
                        current = current.get(field) if isinstance(current, dict) else None
                    valid &= current == value
            detail = "Team-supplied API scenario expectations checked"
        results.append(_result(str(row.scenario), bool(valid), detail))
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", default="data/doctored/processed/demo_scenarios.csv")
    parser.add_argument("--records", required=True)
    parser.add_argument("--expectations")
    parser.add_argument("--output", default="data/reports/rai/scenarios.md")
    args = parser.parse_args()
    records = load_records(args.records)
    expectations = json.loads(Path(args.expectations).read_text(encoding="utf-8")) if args.expectations else None
    results = evaluate_scenarios(args.scenarios, records, expectations=expectations)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Scenario checks",
        "",
        "Scenario names are read from data, never guessed.",
        "Without team expectations, checks cover structural safety only, not product-specific behaviour.",
        "",
        "| Case | Result | Scope |",
        "|---|---|---|",
    ]
    lines += [f"| {row['case']} | {row['status']} | {row['detail']} |" for row in results]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    failures = sum(row["status"] == "FAIL" for row in results)
    print(f"scenarios: {len(results) - failures} PASS, {failures} FAIL")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
