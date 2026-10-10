from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from carbon_engine.factors import FactorRegistry, get_registry
from carbon_engine.ranges import Range
from carbon_engine.schemas import ImpactResult, ImpactStatus, ProductId, ValueRange

ROOT = Path(__file__).resolve().parent.parent
THRESHOLDS_PATH = ROOT / "config" / "thresholds.yaml"
ESTIMATE_LABEL = "Estimated potential impact, not a measured result"


def _load_thresholds() -> dict[str, Any]:
    with THRESHOLDS_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _annual_kwh_from_monthly(monthly: Optional[list[float | int]]) -> float:
    if not monthly:
        return 0.0
    vals = [float(v) for v in monthly if v is not None]
    if not vals:
        return 0.0
    if len(vals) >= 12:
        return sum(vals)
    if len(vals) >= 6:
        return (sum(vals) / len(vals)) * 12.0
    return 0.0


def calculate_solar_impact(
    customer_ctx: dict[str, Any],
    *,
    registry: Optional[FactorRegistry] = None,
    overrides: Optional[dict[str, Any]] = None,
    activity_year: str = "2026",
    country: str = "GB",
) -> ImpactResult:
    registry = registry or get_registry()
    ctx = dict(customer_ctx)
    if overrides:
        ctx.update(overrides)
    thresholds = _load_thresholds()

    customer_id = str(ctx.get("customer_id", "UNKNOWN"))
    cutoff = ctx.get("cutoff_date")
    if isinstance(cutoff, str):
        cutoff = date.fromisoformat(cutoff)
    if cutoff is None:
        cutoff = date.today()

    electricity = ctx.get("electricity_kwh_monthly")
    if electricity in (None, []):
        return ImpactResult(
            customer_id=customer_id,
            product=ProductId.SOLAR_FINANCE,
            status=ImpactStatus.insufficient_data,
            is_estimate=True,
            estimate_label=ESTIMATE_LABEL,
            claim_reduction=False,
            reason_codes=["IMPACT_MISSING_ELECTRICITY_USAGE"],
            cutoff_date=cutoff,
            calculated_at=datetime.now(timezone.utc),
            factor_version=registry.factor_version,
        )

    annual_kwh = _annual_kwh_from_monthly(list(electricity))
    if annual_kwh <= 0:
        return ImpactResult(
            customer_id=customer_id,
            product=ProductId.SOLAR_FINANCE,
            status=ImpactStatus.insufficient_data,
            is_estimate=True,
            estimate_label=ESTIMATE_LABEL,
            claim_reduction=False,
            reason_codes=["IMPACT_MISSING_ELECTRICITY_USAGE"],
            cutoff_date=cutoff,
            calculated_at=datetime.now(timezone.utc),
            factor_version=registry.factor_version,
        )

    if country != "GB":
        return ImpactResult(
            customer_id=customer_id,
            product=ProductId.SOLAR_FINANCE,
            status=ImpactStatus.not_applicable,
            is_estimate=True,
            estimate_label=ESTIMATE_LABEL,
            claim_reduction=False,
            reason_codes=["IMPACT_GEOGRAPHY_MISMATCH"],
            cutoff_date=cutoff,
            calculated_at=datetime.now(timezone.utc),
            factor_version=registry.factor_version,
        )

    grid = registry.get_factor("GRID_ELEC_UK", geography=country, period=activity_year)
    if grid is None:
        return ImpactResult(
            customer_id=customer_id,
            product=ProductId.SOLAR_FINANCE,
            status=ImpactStatus.insufficient_data,
            is_estimate=True,
            estimate_label=ESTIMATE_LABEL,
            claim_reduction=False,
            reason_codes=["IMPACT_MISSING_FACTOR"],
            cutoff_date=cutoff,
            calculated_at=datetime.now(timezone.utc),
            factor_version=registry.factor_version,
        )

    solar_size_min = registry.assumption_range("SOLAR_SIZE_MIN")
    solar_size_max = registry.assumption_range("SOLAR_SIZE_MAX")
    solar_yield = registry.assumption_range("SOLAR_YIELD")
    self_consumption = registry.assumption_range("SOLAR_SELF_CONSUMPTION")
    if None in (solar_size_min, solar_size_max, solar_yield, self_consumption):
        return ImpactResult(
            customer_id=customer_id,
            product=ProductId.SOLAR_FINANCE,
            status=ImpactStatus.insufficient_data,
            is_estimate=True,
            estimate_label=ESTIMATE_LABEL,
            claim_reduction=False,
            reason_codes=["IMPACT_MISSING_FACTOR"],
            cutoff_date=cutoff,
            calculated_at=datetime.now(timezone.utc),
            factor_version=registry.factor_version,
        )

    min_kwp = solar_size_min.central
    max_kwp = solar_size_max.central
    system_kwp = max(min_kwp, min(max_kwp, round(annual_kwh / 1000.0, 1)))

    generation = Range.constant(system_kwp).multiply(solar_yield)
    displaced = Range(
        min(generation.low, annual_kwh),
        min(generation.central, annual_kwh),
        min(generation.high, annual_kwh),
    )
    co2e = displaced.multiply(grid.factor_value)
    claim = co2e.central > 0
    flags: list[str] = []
    if co2e.central < 0:
        claim = False
        flags.append("SCENARIO_NOT_LOWER_THAN_BASELINE")
    if co2e.low < 0:
        flags.append("RANGE_INCLUDES_NO_REDUCTION")

    impact = ImpactResult(
        customer_id=customer_id,
        product=ProductId.SOLAR_FINANCE,
        status=ImpactStatus.estimated,
        is_estimate=True,
        estimate_label=ESTIMATE_LABEL,
        claim_reduction=claim,
        impact_type="annual_grid_electricity_displaced",
        co2e=ValueRange(low=co2e.low, central=co2e.central, high=co2e.high, unit="kg_CO2e/year"),
        energy={
            "displaced_kwh": {
                "low": displaced.low,
                "central": displaced.central,
                "high": displaced.high,
                "unit": "kWh/year",
            },
            "annual_grid_use_kwh": {
                "low": annual_kwh,
                "central": annual_kwh,
                "high": annual_kwh,
                "unit": "kWh/year",
            },
            "system_kwp": {
                "low": system_kwp,
                "central": system_kwp,
                "high": system_kwp,
                "unit": "kWp",
            },
        },
        method="SOLAR_SELF_CONSUMED_X_GRID_FACTOR_v1",
        input_quality="FULL_12M" if len([v for v in electricity if v is not None]) >= 12 else "ANNUALISED_PARTIAL",
        factor_ids=["GRID_ELEC_UK"],
        factor_version=registry.factor_version,
        assumption_ids=["SOLAR_YIELD", "SOLAR_SELF_CONSUMPTION", "SOLAR_SIZE_MIN", "SOLAR_SIZE_MAX"],
        provenance_grade=registry.provenance_grade(["GRID_ELEC_UK"]),
        assumptions=[
            "Self-consumed solar only; export not included in avoided emissions",
            "Annual grid use is capped by displaced solar generation",
        ],
        limitations=["Estimate, not a measured outcome"],
        reason_codes=[],
        cutoff_date=cutoff,
        calculated_at=datetime.now(timezone.utc),
        flags=flags,
    )
    return impact
