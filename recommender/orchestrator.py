from __future__ import annotations

from datetime import date
from typing import Any, Optional

from carbon_engine.router import calculate_impact
from carbon_engine.schemas import (
    BusinessRecommendations,
    CustomerRecommendations,
    EligibilityResult,
    MLPayload,
    Opportunity,
    ProductId,
)
from eligibility.engine import evaluate_eligibility
from recommender.gate import evaluate_gate, validate_ml_payload
from recommender.priority import compute_priority, rank_opportunities


def _decision_codes(eligibility: EligibilityResult) -> list[str]:
    return [f"{d.rule_id}:{d.outcome.value}" for d in eligibility.decisions]


def evaluate_opportunity(
    customer_ctx: dict[str, Any],
    ml_payload: MLPayload | dict[str, Any],
    product: ProductId | str,
    *,
    p95_by_product: Optional[dict[str, float]] = None,
    impact_overrides: Optional[dict[str, Any]] = None,
    run_date: Optional[date] = None,
) -> Opportunity:
    ml = validate_ml_payload(ml_payload)
    product_enum = product if isinstance(product, ProductId) else ProductId(product)
    p95_by_product = p95_by_product or {}

    eligibility = evaluate_eligibility(customer_ctx, product_enum.value, run_date=run_date)
    impact = calculate_impact(
        customer_ctx,
        product_enum,
        eligibility.eligibility_status,
        overrides=impact_overrides,
    )
    gate = evaluate_gate(
        eligibility.eligibility_status,
        ml,
        impact,
        no_automated_customer_message=eligibility.no_automated_customer_message,
    )
    priority = compute_priority(ml, impact, p95_by_product)

    cutoff = customer_ctx.get("cutoff_date")
    if isinstance(cutoff, str):
        cutoff = date.fromisoformat(cutoff)
    if cutoff is None:
        cutoff = date.today()

    outcome_window = int(
        customer_ctx.get("outcome_window_days")
        or 90
    )

    return Opportunity(
        customer_id=str(customer_ctx.get("customer_id", "UNKNOWN")),
        product=product_enum,
        propensity=ml.propensity,
        confidence=ml.confidence,
        reason_codes=list(ml.reason_codes),
        eligibility_result=eligibility.eligibility_status,
        eligibility_conditions=list(eligibility.conditions),
        decision_codes=_decision_codes(eligibility),
        gate=gate,
        impact=impact,
        priority=priority,
        cutoff_date=cutoff,
        outcome_window_days=outcome_window,
        data_timestamp=cutoff,
        model_version=ml.model_version,
        rule_version=eligibility.rule_version,
        factor_version=impact.factor_version,
        audience={
            "customer_visible": gate.present_to_customer,
            "business_queue": gate.present_to_business,
        },
    )


def evaluate_customer_products(
    customer_ctx: dict[str, Any],
    ml_by_product: dict[str, MLPayload | dict[str, Any]],
    products: Optional[list[ProductId | str]] = None,
    *,
    p95_by_product: Optional[dict[str, float]] = None,
    run_date: Optional[date] = None,
) -> CustomerRecommendations:
    products = products or list(ProductId)
    p95_by_product = p95_by_product or {}
    opportunities: list[Opportunity] = []

    for prod in products:
        ml = ml_by_product.get(str(prod))
        if ml is None:
            continue
        opp = evaluate_opportunity(
            customer_ctx,
            ml,
            prod,
            p95_by_product=p95_by_product,
            run_date=run_date,
        )
        if opp.gate.present_to_customer:
            opportunities.append(opp)

    ranked = rank_opportunities(opportunities)
    primary = ranked[0] if ranked else None
    secondary = ranked[1:] if len(ranked) > 1 else []

    cutoff = customer_ctx.get("cutoff_date")
    if isinstance(cutoff, str):
        cutoff = date.fromisoformat(cutoff)
    if cutoff is None:
        cutoff = date.today()

    return CustomerRecommendations(
        customer_id=str(customer_ctx.get("customer_id", "UNKNOWN")),
        primary=primary,
        secondary=secondary,
        cutoff_date=cutoff,
        outcome_window_days=int(customer_ctx.get("outcome_window_days") or 90),
    )


def evaluate_business_view(
    customer_ctx: dict[str, Any],
    ml_by_product: dict[str, MLPayload | dict[str, Any]],
    products: Optional[list[ProductId | str]] = None,
    *,
    p95_by_product: Optional[dict[str, float]] = None,
    run_date: Optional[date] = None,
) -> BusinessRecommendations:
    products = products or list(ProductId)
    p95_by_product = p95_by_product or {}
    queue: list[Opportunity] = []
    blocked: list[dict[str, Any]] = []

    for prod in products:
        ml = ml_by_product.get(str(prod))
        if ml is None:
            continue
        opp = evaluate_opportunity(
            customer_ctx,
            ml,
            prod,
            p95_by_product=p95_by_product,
            run_date=run_date,
        )
        if opp.gate.present_to_business:
            queue.append(opp)
        elif not opp.gate.passed:
            blocked.append(
                {
                    "product": opp.product.value,
                    "gate_codes": opp.gate.codes,
                    "eligibility": opp.eligibility_result.value,
                    "propensity": opp.propensity,
                }
            )

    queue = rank_opportunities(queue)
    cutoff = customer_ctx.get("cutoff_date")
    if isinstance(cutoff, str):
        cutoff = date.fromisoformat(cutoff)
    if cutoff is None:
        cutoff = date.today()

    return BusinessRecommendations(
        customer_id=str(customer_ctx.get("customer_id", "UNKNOWN")),
        queue=queue,
        blocked=blocked,
        cutoff_date=cutoff,
    )
