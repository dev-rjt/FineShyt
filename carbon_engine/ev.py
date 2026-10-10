from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

import yaml
from pathlib import Path

from carbon_engine.factors import FactorRegistry, get_registry
from carbon_engine.ranges import Range, reduction_from_baseline_scenario
from carbon_engine.schemas import (
    ImpactResult,
    ImpactStatus,
    ProductId,
    ValueRange,
)
from carbon_engine.units import UnitConversionError, convert_distance_to_km

ROOT = Path(__file__).resolve().parent.parent
THRESHOLDS_PATH = ROOT / "config" / "thresholds.yaml"

ICE_FACTOR_MAP = {
    "PETROL": "CAR_PETROL_AVG_KM",
    "DIESEL": "CAR_DIESEL_AVG_KM",
    "HYBRID": "CAR_HYBRID_AVG_KM",
    "PHEV": "CAR_PHEV_AVG_KM",
}

ESTIMATE_LABEL = "Estimated potential impact, not a measured result"


def _load_thresholds() -> dict[str, Any]:
    with THRESHOLDS_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _get_field(ctx: dict[str, Any], key: str) -> Any:
    if key not in ctx:
        return None
    return ctx[key]


def _missing_result(
    customer_id: str,
    cutoff: date,
    codes: list[str],
    registry: FactorRegistry,
) -> ImpactResult:
    return ImpactResult(
        customer_id=customer_id,
        product=ProductId.EV_FINANCE,
        status=ImpactStatus.insufficient_data,
        is_estimate=True,
        estimate_label=ESTIMATE_LABEL,
        claim_reduction=False,
        co2e=None,
        energy=None,
        paper=None,
        digital_adoption=None,
        reason_codes=codes,
        cutoff_date=cutoff,
        calculated_at=datetime.now(timezone.utc),
        factor_version=registry.factor_version,
    )


def _not_applicable(
    customer_id: str,
    cutoff: date,
    reason: str,
    registry: FactorRegistry,
) -> ImpactResult:
    return ImpactResult(
        customer_id=customer_id,
        product=ProductId.EV_FINANCE,
        status=ImpactStatus.not_applicable,
        is_estimate=True,
        estimate_label=ESTIMATE_LABEL,
        claim_reduction=False,
        reason_codes=[reason],
        cutoff_date=cutoff,
        calculated_at=datetime.now(timezone.utc),
        factor_version=registry.factor_version,
    )


def resolve_distance_km(
    ctx: dict[str, Any], thresholds: dict[str, Any]
) -> tuple[Optional[Range], Optional[str], list[str]]:
    """Returns (distance range, input_quality, limitations)."""
    limitations: list[str] = []
    dist = _get_field(ctx, "annual_distance")
    if dist is not None:
        unit = _get_field(ctx, "annual_distance_unit") or "km"
        try:
            km = convert_distance_to_km(float(dist), unit)
        except UnitConversionError as e:
            raise e
        source = _get_field(ctx, "annual_distance_source") or "DECLARED"
        iq = thresholds.get("input_quality", {})
        frac = iq.get(source, iq.get("DECLARED", 0.10))
        r = Range(km, km, km).widen_by_fraction(frac)
        return r, source, limitations

    spend = _get_field(ctx, "annual_fuel_spend_gbp")
    allow = thresholds.get("allow_spend_derived_distance", True)
    if spend is not None and float(spend) > 0 and allow:
        registry = get_registry()
        price = registry.assumption_range("FUEL_PRICE_PER_LITRE")
        km_per_l = registry.assumption_range("ICE_KM_PER_LITRE")
        if price is None or km_per_l is None:
            return None, None, []
        spend_r = Range(float(spend), float(spend), float(spend))
        litres = Range(
            spend_r.low / price.high,
            spend_r.central / price.central,
            spend_r.high / price.low,
        )
        km_r = Range(
            litres.low * km_per_l.low,
            litres.central * km_per_l.central,
            litres.high * km_per_l.high,
        )
        frac = thresholds.get("input_quality", {}).get("SPEND_DERIVED", 0.25)
        km_r = km_r.widen_by_fraction(frac)
        limitations.append("DISTANCE_DERIVED_FROM_SPEND")
        return km_r, "SPEND_DERIVED", limitations

    return None, None, limitations


def calculate_ev_impact(
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

    limitations: list[str] = ["Estimate, not a measured outcome"]
    assumptions_text = [
        "Annual distance unchanged after switching",
        "EV efficiency from assumption register",
    ]

    try:
        distance_km, input_quality, dist_limits = resolve_distance_km(ctx, thresholds)
    except UnitConversionError:
        return ImpactResult(
            customer_id=customer_id,
            product=ProductId.EV_FINANCE,
            status=ImpactStatus.calculation_error,
            is_estimate=True,
            estimate_label=ESTIMATE_LABEL,
            claim_reduction=False,
            reason_codes=["UNSUPPORTED_UNIT"],
            cutoff_date=cutoff,
            calculated_at=datetime.now(timezone.utc),
            factor_version=registry.factor_version,
        )

    limitations.extend(dist_limits)

    if distance_km is None:
        return _missing_result(
            customer_id, cutoff, ["IMPACT_MISSING_ANNUAL_DISTANCE"], registry
        )

    fuel_type = _get_field(ctx, "vehicle_fuel_type")
    if fuel_type is None and (_get_field(ctx, "annual_fuel_spend_gbp") or 0) <= 0:
        return _missing_result(
            customer_id, cutoff, ["IMPACT_MISSING_VEHICLE_FUEL_TYPE"], registry
        )
    if fuel_type is None:
        fuel_type = "PETROL"

    factor_id = ICE_FACTOR_MAP.get(str(fuel_type))
    if factor_id is None:
        if fuel_type == "BEV":
            factor_id = ICE_FACTOR_MAP["PETROL"]
        else:
            return _missing_result(
                customer_id, cutoff, ["IMPACT_MISSING_VEHICLE_FUEL_TYPE"], registry
            )

    ice_factor = registry.get_factor(factor_id, geography=country, period=activity_year)
    grid = registry.get_factor("GRID_ELEC_UK", geography=country, period=activity_year)
    ev_kwh = registry.assumption_range("EV_KWH_PER_KM")

    if ice_factor is None or grid is None or ev_kwh is None:
        return _missing_result(
            customer_id, cutoff, ["IMPACT_MISSING_FACTOR"], registry
        )

    if country != "GB":
        return _not_applicable(customer_id, cutoff, "IMPACT_GEOGRAPHY_MISMATCH", registry)

    if ice_factor.boundary != grid.boundary and not (
        ice_factor.boundary == "UNCONFIRMED" and grid.boundary == "UNCONFIRMED"
    ):
        if ice_factor.boundary != grid.boundary:
            return ImpactResult(
                customer_id=customer_id,
                product=ProductId.EV_FINANCE,
                status=ImpactStatus.calculation_error,
                is_estimate=True,
                estimate_label=ESTIMATE_LABEL,
                claim_reduction=False,
                reason_codes=["BOUNDARY_MISMATCH"],
                cutoff_date=cutoff,
                calculated_at=datetime.now(timezone.utc),
                factor_version=registry.factor_version,
            )

    ice_val = ice_factor.factor_value
    grid_val = grid.factor_value

    baseline = distance_km.multiply(ice_val)
    scenario = distance_km.multiply(ev_kwh).multiply(grid_val)
    reduction = reduction_from_baseline_scenario(baseline, scenario)

    claim = True
    flags: list[str] = []
    if reduction.central < 0:
        claim = False
        limitations.append("SCENARIO_NOT_LOWER_THAN_BASELINE")
    if reduction.low < 0:
        flags.append("RANGE_INCLUDES_NO_REDUCTION")

    factor_ids = [factor_id, "GRID_ELEC_UK"]
    provenance = registry.provenance_grade(factor_ids)
    if provenance == "PROVISIONAL":
        limitations.append("Illustrative factors")

    if distance_km.central == 0:
        reduction = Range(0.0, 0.0, 0.0)
        baseline = Range(0.0, 0.0, 0.0)
        scenario = Range(0.0, 0.0, 0.0)

    def to_vr(r: Range, unit: str) -> ValueRange:
        return ValueRange(low=r.low, central=r.central, high=r.high, unit=unit)

    return ImpactResult(
        customer_id=customer_id,
        product=ProductId.EV_FINANCE,
        status=ImpactStatus.estimated,
        is_estimate=True,
        estimate_label=ESTIMATE_LABEL,
        claim_reduction=claim,
        impact_type="annual_emissions_reduction",
        co2e=to_vr(reduction, "kg_CO2e/year"),
        energy=None,
        paper=None,
        digital_adoption=None,
        baseline=to_vr(baseline, "kg_CO2e/year"),
        scenario=to_vr(scenario, "kg_CO2e/year"),
        method="EV_ANNUAL_DISTANCE_X_FACTOR_v1",
        input_quality=input_quality,
        factor_ids=factor_ids,
        factor_version=registry.factor_version,
        assumption_ids=["EV_KWH_PER_KM"],
        provenance_grade=provenance,
        assumptions=assumptions_text,
        limitations=limitations,
        reason_codes=[],
        cutoff_date=cutoff,
        calculated_at=datetime.now(timezone.utc),
        flags=flags,
    )
