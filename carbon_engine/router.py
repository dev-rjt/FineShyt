from __future__ import annotations

from typing import Any, Optional

from carbon_engine.ev import calculate_ev_impact
from carbon_engine.factors import FactorRegistry
from carbon_engine.green_home import calculate_green_home_impact
from carbon_engine.paperless import calculate_paperless_impact
from carbon_engine.schemas import (
    EligibilityStatus,
    ImpactResult,
    ImpactStatus,
    ProductId,
)
from carbon_engine.solar import calculate_solar_impact
from datetime import date, datetime, timezone


def calculate_impact(
    customer_ctx: dict[str, Any],
    product: ProductId | str,
    eligibility_status: EligibilityStatus,
    *,
    registry: Optional[FactorRegistry] = None,
    overrides: Optional[dict[str, Any]] = None,
) -> ImpactResult:
    product = ProductId(product)
    registry = registry or FactorRegistry()

    if eligibility_status not in (
        EligibilityStatus.ELIGIBLE,
        EligibilityStatus.ELIGIBLE_WITH_CONDITIONS,
    ):
        reason = (
            "INSUFFICIENT_DATA"
            if eligibility_status == EligibilityStatus.INSUFFICIENT_DATA
            else "BLOCKED_BY_ELIGIBILITY"
        )
        cutoff = customer_ctx.get("cutoff_date")
        if isinstance(cutoff, str):
            cutoff = date.fromisoformat(cutoff)
        if cutoff is None:
            cutoff = date.today()
        return ImpactResult(
            customer_id=str(customer_ctx.get("customer_id", "UNKNOWN")),
            product=product,
            status=ImpactStatus.not_applicable,
            is_estimate=True,
            estimate_label="Estimated potential impact, not a measured result",
            claim_reduction=False,
            reason_codes=[reason],
            cutoff_date=cutoff,
            calculated_at=datetime.now(timezone.utc),
            factor_version=registry.factor_version,
        )

    if product == ProductId.EV_FINANCE:
        return calculate_ev_impact(customer_ctx, registry=registry, overrides=overrides)
    if product == ProductId.SOLAR_FINANCE:
        return calculate_solar_impact(customer_ctx, registry=registry, overrides=overrides)
    if product == ProductId.GREEN_HOME:
        return calculate_green_home_impact(customer_ctx, registry=registry, overrides=overrides)
    if product == ProductId.PAPERLESS_BANKING:
        return calculate_paperless_impact(customer_ctx, registry=registry, overrides=overrides)

    cutoff = customer_ctx.get("cutoff_date")
    if isinstance(cutoff, str):
        cutoff = date.fromisoformat(cutoff)
    if cutoff is None:
        cutoff = date.today()
    return ImpactResult(
        customer_id=str(customer_ctx.get("customer_id", "UNKNOWN")),
        product=product,
        status=ImpactStatus.not_applicable,
        is_estimate=True,
        estimate_label="Estimated potential impact, not a measured result",
        claim_reduction=False,
        reason_codes=["PRODUCT_CALCULATOR_NOT_IMPLEMENTED"],
        cutoff_date=cutoff,
        calculated_at=datetime.now(timezone.utc),
        factor_version=registry.factor_version,
    )
