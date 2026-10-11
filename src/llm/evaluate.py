"""Reproducible synthetic integration scenarios; no claims about live quality."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

from responsible_ai.contract_checks import validate_record

from .__main__ import write_records
from .engine import ExplanationEngine, component_versions
from .providers import OllamaProvider
from .verifier import strict_json_loads

def scenarios():
    # Existing PDF fixtures remain unchanged. Fragments are completed only here.
    root = Path(__file__).resolve().parents[2]
    fixtures = root / "tests" / "fixtures"
    base = strict_json_loads((fixtures / "eligible_ev.json").read_text())
    cases = []
    for name, file in (
        ("eligible_ev", "eligible_ev.json"), ("ineligible_ev", "ineligible_ev.json"),
        ("missing_data_ev", "missing_data_ev.json"), ("calculation_error", "calculation_error.json"),
        ("manual_review", "conflicting_signals.json"),
    ):
        record = deepcopy(base)
        record.update(strict_json_loads((fixtures / file).read_text()))
        # Fixtures' explanation text is illustrative and is replaced by the engine.
        record["explanation"] = {"status": "NOT_GENERATED", "headline": None, "customer_message": None,
                                 "manager_message": None, "verification": {"passed": False, "verified_fields": [],
                                  "unsupported_claims": [], "fallback_used": False},
                                 "llm": {"provider": None, "model": None, "prompt_version": None}}
        record["audit"]["component_versions"].update(component_versions())
        if record["eligibility"]["requires_human_review"]:
            record["audit"]["human_review_required"] = True
        cases.append((name, record))
    for product, product_id, name, category in (
        ("GREEN_HOME_LOAN", "GP02", "Green Home Loan", "HOME"),
        ("SOLAR_FINANCE", "GP03", "Solar Finance", "HOME"),
        ("PAPERLESS_BANKING", "GP04", "Paperless Banking", "DIGITAL"),
    ):
        record = deepcopy(cases[0][1])
        record["opportunity"] = {"product_id": product_id, "product_code": product,
                                 "product_name": name, "category": category}
        # Deliberately unavailable impact: never reuse EV estimates for other products.
        record["impact"] = {"status": "INSUFFICIENT_DATA"}
        record["prediction"]["reason_codes"] = []
        record["recommendation"]["action_code"] = None
        record["recommendation"]["action_label"] = None
        record["eligibility"]["decision_codes"] = []
        cases.append((product.lower() + "_synthetic", record))
    return cases


def evaluate(engine):
    cases = []
    for name, record in scenarios():
        output = engine.generate(record)
        explanation = output["explanation"]
        allowed = record["recommendation"]["customer_visible"]
        checks = {
            "contract_valid": not validate_record(output, before_llm=record),
            "customer_visibility": (explanation["customer_message"] is not None) == allowed,
            "manager_visibility": (explanation["manager_message"] is not None) == record["recommendation"]["manager_visible"],
            "final_verification": explanation["verification"]["passed"],
            "timestamp_present": record["data_cutoff_date"] in (explanation["manager_message"] or ""),
        }
        cases.append({"case": name, "status": explanation["status"], "checks": checks})
    count = len(cases)
    return {"evaluation_basis": "synthetic contract scenarios; structural grounding only",
            "cases": cases, "case_count": count,
            "passed_case_count": sum(all(case["checks"].values()) for case in cases),
            "llm_acceptance_rate": sum(case["status"] == "VERIFIED" for case in cases) / count,
            "fallback_rate": sum(case["status"] == "FALLBACK_USED" for case in cases) / count,
            "limitations": ["No held-out human readability or factual-quality labels",
                            "No live LLM quality conclusion from template or mocked runs",
                            "Upstream facts and official rules require independent validation"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate synthetic LLM integration scenarios")
    parser.add_argument("--provider", choices=("template", "ollama"), default="template")
    parser.add_argument("--output", required=True, help="New report JSON path")
    args = parser.parse_args(argv)
    try:
        provider = OllamaProvider.from_env() if args.provider == "ollama" else None
        report = evaluate(ExplanationEngine(provider))
        write_records(args.output, [report])
    except (ValueError, OSError):
        print("LLM evaluation failed: check configuration, contract scenarios and new output path.", file=sys.stderr)
        return 1
    print(json.dumps({key: report[key] for key in ("case_count", "passed_case_count", "llm_acceptance_rate", "fallback_rate")}))
    return int(report["passed_case_count"] != report["case_count"])


if __name__ == "__main__":
    raise SystemExit(main())
