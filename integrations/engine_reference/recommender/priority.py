from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

from carbon_engine.ranges import clamp_range_value
from carbon_engine.schemas import ImpactResult, ImpactStatus, MLPayload, PriorityDetail, ProductId

ROOT = Path(__file__).resolve().parent.parent
THRESHOLDS_PATH = ROOT / "config" / "thresholds.yaml"


def _thresholds() -> dict[str, Any]:
    with THRESHOLDS_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def impact_central_for_norm(impact: ImpactResult) -> Optional[float]:
    if impact.status != ImpactStatus.estimated:
        return None
    if impact.product == ProductId.PAPERLESS_BANKING:
        paper = impact.paper or {}
        sheets = paper.get("sheets_avoided")
        if sheets is None:
            return None
        if isinstance(sheets, dict):
            return sheets.get("central")
        return None
    if impact.co2e is None:
        return None
    return getattr(impact.co2e, "central", None)


def compute_impact_norm(
    impact: ImpactResult,
    p95_by_product: dict[str, float],
) -> float:
    thr = _thresholds()
    floor = float(thr.get("impact_norm_floor", 0.10))

    if impact.status == ImpactStatus.insufficient_data:
        return floor

    central = impact_central_for_norm(impact)
    if central is None:
        return floor

    p95 = p95_by_product.get(impact.product.value, 0.0)
    if p95 <= 0:
        return floor if central <= 0 else 1.0

    return clamp_range_value(central / p95, 0.0, 1.0)


def compute_priority(
    ml: MLPayload,
    impact: ImpactResult,
    p95_by_product: dict[str, float],
) -> PriorityDetail:
    impact_norm = compute_impact_norm(impact, p95_by_product)
    score = ml.propensity * ml.confidence * impact_norm
    return PriorityDetail(
        score=score,
        impact_norm=impact_norm,
        propensity=ml.propensity,
        confidence=ml.confidence,
    )


def rank_opportunities(
    opportunities: list[Any],
) -> list[Any]:
    """Sort by priority score descending; assign rank_within_customer."""

    sorted_opps = sorted(
        opportunities,
        key=lambda o: o.priority.score,
        reverse=True,
    )
    for i, opp in enumerate(sorted_opps, start=1):
        opp.priority.rank_within_customer = i
    return sorted_opps
