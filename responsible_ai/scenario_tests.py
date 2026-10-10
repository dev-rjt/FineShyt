"""Record-based scenarios; no eligibility engine or carbon calculations."""
import argparse
import copy
import json
from pathlib import Path

import pandas as pd

from responsible_ai.contract_checks import load_records, validate_record


def _result(name, ok, detail):
    return {"case": name, "status": "PASS" if ok else "FAIL", "detail": detail}


def guard_cases():
    """Mutate documented fixtures to test validation, not product rules."""
    fixtures = Path(__file__).resolve().parents[1] / "tests/fixtures"
    base = json.loads((fixtures / "eligible_ev.json").read_text())
    ineligible = copy.deepcopy(base)
    ineligible.update(json.loads((fixtures / "ineligible_ev.json").read_text()))
    missing = copy.deepcopy(base)
    missing.update(json.loads((fixtures / "missing_data_ev.json").read_text()))
    missing["audit"]["human_review_required"] = True
    missing["explanation"] = json.loads((fixtures / "calculation_error.json").read_text())["explanation"]
    error = json.loads((fixtures / "calculation_error.json").read_text())
    # Never carry the canonical eligible explanation into a blocked fragment.
    ineligible["explanation"] = copy.deepcopy(error["explanation"])
    results = []
    for name, record in [("HIGH_PROPENSITY_INELIGIBLE", ineligible),
                         ("INSUFFICIENT_DATA", missing), ("CALCULATION_ERROR", error)]:
        results.append(_result(name, not validate_record(record), "Documented/illustrative abstention record accepted"))
        unsafe = copy.deepcopy(record)
        unsafe["recommendation"]["customer_visible"] = True
        # Eligible + DO_NOT_RECOMMEND still fails the visibility gate.
        results.append(_result(name + "_VISIBILITY_BLOCK", bool(validate_record(unsafe)),
                               "Invalid customer visibility rejected"))
    manual = copy.deepcopy(missing)
    manual["recommendation"]["decision"] = "RECOMMEND"
    manual["recommendation"]["customer_visible"] = True
    results.append(_result("MANUAL_REVIEW_NOT_VISIBLE", bool(validate_record(manual)), "Manual review cannot recommend"))
    for state in ["INSUFFICIENT_DATA", "NOT_APPLICABLE", "CALCULATION_ERROR"]:
        invalid = copy.deepcopy(base)
        invalid["impact"]["status"] = state
        for key in ["lower_estimate", "central_estimate", "upper_estimate"]:
            invalid["impact"]["primary_metric"][key] = 0
        results.append(_result(state + "_ZERO_REJECTED", bool(validate_record(invalid)),
                               "Unavailable impact carrying zero estimates rejected"))
    null_record = copy.deepcopy(missing)
    null_record["impact"]["primary_metric"] = None
    validate_record(null_record)
    results.append(_result("NULL_STAYS_NULL", null_record["impact"]["primary_metric"] is None,
                           "Validation never imputes zero"))
    return results


def evaluate_scenarios(scenario_path, records, *, expectations=None):
    scenarios = pd.read_csv(scenario_path)
    if list(scenarios.columns) != ["customer_id", "scenario"] or scenarios.isna().any().any():
        raise ValueError("Invalid demo_scenarios structure")
    results = guard_cases()
    for index, row in scenarios.iterrows():
        matches = [r for r in records if r.get("customer", {}).get("customer_id") == row.customer_id]
        valid = bool(matches) and all(not validate_record(r) for r in matches)
        detail = "Records exist and satisfy safety invariants; scenario meaning not asserted"
        expected = (expectations or {}).get(row.scenario)
        if expected:
            # Team-supplied mapping uses existing contract field paths only.
            product = expected["product_code"]
            matches = [r for r in matches if r.get("opportunity", {}).get("product_code") == product]
            valid &= bool(matches)
            for record in matches:
                for path, value in expected["fields"].items():
                    current = record
                    for field in path.split("."):
                        current = current.get(field) if isinstance(current, dict) else None
                    valid &= current == value
            detail = "Team-supplied scenario expectations checked"
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
    expectations = json.loads(Path(args.expectations).read_text()) if args.expectations else None
    results = evaluate_scenarios(args.scenarios, records, expectations=expectations)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Scenario checks", "", "Scenario names are read from data, never guessed.",
             "Without team expectations, checks cover structural safety only, not product-specific behaviour.",
             "", "| Case | Result | Scope |", "|---|---|---|"]
    lines += [f"| {r['case']} | {r['status']} | {r['detail']} |" for r in results]
    output.write_text("\n".join(lines) + "\n")
    failures = sum(r["status"] == "FAIL" for r in results)
    print(f"scenarios: {len(results) - failures} PASS, {failures} FAIL")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
