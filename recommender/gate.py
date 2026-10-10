from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from carbon_engine.schemas import (
    EligibilityStatus,
    GateResult,
    ImpactResult,
    ImpactStatus,
    MLPayload,
    ProductId,
)

ROOT = Path(__file__).resolve().parent.parent
THRESHOLDS_PATH = ROOT / "config" / "thresholds.yaml"
REASON_CODES_PATH = ROOT / "config" / "reason_codes.yaml"


class InvalidMLPayload(ValueError):
    code = "INVALID_ML_PAYLOAD"


def load_reason_codes(path: Path = REASON_CODES_PATH) -> set[str]:
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    return set(doc.get("codes", []))


def validate_ml_payload(payload: MLPayload | dict[str, Any]) -> MLPayload:
    if isinstance(payload, dict):
        try:
            payload = MLPayload.model_validate(payload)
        except Exception as e:
            raise InvalidMLPayload(str(e)) from e
    registered = load_reason_codes()
    for code in payload.reason_codes:
        if code not in registered:
            raise InvalidMLPayload(f"Unknown reason code: {code}")
    return payload


def _thresholds() -> dict[str, Any]:
    with THRESHOLDS_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _min_propensity(product: ProductId, thr: dict[str, Any]) -> float:
    by_prod = thr.get("min_propensity_by_product") or {}
    return float(by_prod.get(product.value, thr.get("min_propensity", 0.50)))


def _min_confidence(product: ProductId, thr: dict[str, Any]) -> float:
    by_prod = thr.get("min_confidence_by_product") or {}
    return float(by_prod.get(product.value, thr.get("min_confidence", 0.50)))


def evaluate_gate(
    eligibility_status: EligibilityStatus,
    ml: MLPayload,
    impact: ImpactResult,
    *,
    no_automated_customer_message: bool = False,
) -> GateResult:
    thr = _thresholds()
    codes: list[str] = []

    if eligibility_status not in (
        EligibilityStatus.ELIGIBLE,
        EligibilityStatus.ELIGIBLE_WITH_CONDITIONS,
    ):
        codes.append("GATE_BLOCKED_ELIGIBILITY")

    if ml.propensity < _min_propensity(impact.product, thr):
        codes.append("GATE_LOW_PROPENSITY")
    if ml.confidence < _min_confidence(impact.product, thr):
        codes.append("GATE_LOW_CONFIDENCE")

    if impact.product != ProductId.PAPERLESS_BANKING:
        if impact.status == ImpactStatus.estimated and impact.co2e is not None:
            central = getattr(impact.co2e, "central", None)
            if central is not None and central <= 0 and not impact.claim_reduction:
                codes.append("GATE_NO_REDUCTION")

    passed = len(codes) == 0
    present_customer = passed and not no_automated_customer_message
    present_business = passed or (
        eligibility_status == EligibilityStatus.NOT_ELIGIBLE
        and ml.propensity >= _min_propensity(impact.product, thr)
    )

    return GateResult(
        passed=passed,
        codes=codes,
        present_to_customer=present_customer,
        present_to_business=present_business and passed,
    )
