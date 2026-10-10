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


def calculate_green_home_impact(
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

    gas_monthly = ctx.get("gas_kwh_monthly")
    elec_monthly = ctx.get("electricity_kwh_monthly")
    if gas_monthly in (None, []):
        return ImpactResult(
            customer_id=customer_id,
            product=ProductId.GREEN_HOME,
            status=ImpactStatus.insufficient_data,
            is_estimate=True,
            estimate_label=ESTIMATE_LABEL,
            claim_reduction=False,
            reason_codes=["IMPACT_MISSING_GAS_USAGE"],
            cutoff_date=cutoff,
            calculated_at=datetime.now(timezone.utc),
            factor_version=registry.factor_version,
        )

    annual_gas = _annual_kwh_from_monthly(list(gas_monthly))
    annual_elec = _annual_kwh_from_monthly(list(elec_monthly) if elec_monthly else [])
    if annual_gas <= 0:
        return ImpactResult(
            customer_id=customer_id,
            product=ProductId.GREEN_HOME,
            status=ImpactStatus.insufficient_data,
            is_estimate=True,
            estimate_label=ESTIMATE_LABEL,
            claim_reduction=False,
            reason_codes=["IMPACT_MISSING_GAS_USAGE"],
            cutoff_date=cutoff,
            calculated_at=datetime.now(timezone.utc),
            factor_version=registry.factor_version,
        )

    if country != "GB":
        return ImpactResult(
            customer_id=customer_id,
            product=ProductId.GREEN_HOME,
            status=ImpactStatus.not_applicable,
            is_estimate=True,
            estimate_label=ESTIMATE_LABEL,
            claim_reduction=False,
            reason_codes=["IMPACT_GEOGRAPHY_MISMATCH"],
            cutoff_date=cutoff,
            calculated_at=datetime.now(timezone.utc),
            factor_version=registry.factor_version,
        )

    gas_factor = registry.get_factor("GAS_NATURAL_GCV", geography=country, period=activity_year)
    grid_factor = registry.get_factor("GRID_ELEC_UK", geography=country, period=activity_year)
    boiler_eff = registry.assumption_range("BOILER_EFFICIENCY")
    hp_scop = registry.assumption_range("HP_SCOP")
    insulation_reduction = registry.assumption_range("HEATING_REDUCTION_LOFT_WALL")
    if None in (gas_factor, grid_factor, boiler_eff, hp_scop, insulation_reduction):
        return ImpactResult(
            customer_id=customer_id,
            product=ProductId.GREEN_HOME,
            status=ImpactStatus.insufficient_data,
            is_estimate=True,
            estimate_label=ESTIMATE_LABEL,
            claim_reduction=False,
            reason_codes=["IMPACT_MISSING_FACTOR"],
            cutoff_date=cutoff,
            calculated_at=datetime.now(timezone.utc),
            factor_version=registry.factor_version,
        )

    monthly = list(gas_monthly)
    if len(monthly) >= 12:
        baseload = (monthly[5] + monthly[6] + monthly[7]) / 3.0 * 12.0
    else:
        baseload = _annual_kwh_from_monthly(monthly) * 0.5
    heating_gas = max(0.0, annual_gas - baseload)

    heating_type = str(ctx.get("heating_type") or "")
    insulation = str(ctx.get("insulation_status") or "UNKNOWN")
    heat_pump_threshold = float(thresholds.get("green_home", {}).get("heat_pump_min_heating_gas_kwh", 3000))
    insulation_threshold = float(thresholds.get("green_home", {}).get("insulation_min_heating_gas_kwh", 1500))

    if heating_type == "GAS_BOILER" and heating_gas >= heat_pump_threshold:
        intervention = "HEAT_PUMP"
    elif insulation in {"NONE", "PARTIAL", "UNKNOWN"} and heating_gas >= insulation_threshold:
        intervention = "LOFT_AND_WALL_INSULATION"
    else:
        return ImpactResult(
            customer_id=customer_id,
            product=ProductId.GREEN_HOME,
            status=ImpactStatus.not_applicable,
            is_estimate=True,
            estimate_label=ESTIMATE_LABEL,
            claim_reduction=False,
            reason_codes=["NO_APPLICABLE_INTERVENTION"],
            cutoff_date=cutoff,
            calculated_at=datetime.now(timezone.utc),
            factor_version=registry.factor_version,
        )

    if intervention == "HEAT_PUMP":
        baseline = Range.constant(annual_gas).multiply(gas_factor.factor_value).add(
            Range.constant(annual_elec).multiply(grid_factor.factor_value)
        )
        heat_delivered = Range.constant(heating_gas).multiply(boiler_eff)
        hp_electricity = heat_delivered.divide(hp_scop)
        scenario_gas = Range.constant(max(0.0, annual_gas - heating_gas))
        scenario = scenario_gas.multiply(gas_factor.factor_value).add(
            Range.constant(annual_elec + hp_electricity.central).multiply(grid_factor.factor_value)
        )
        scenario = Range(
            scenario.low,
            scenario.central,
            scenario.high,
        )
        reduction = baseline.subtract(scenario)
        change_kwh = Range.constant(annual_gas - heating_gas).subtract(Range.constant(annual_gas))
        energy = {
            "baseline_kwh": {"low": baseline.low, "central": baseline.central, "high": baseline.high, "unit": "kg_CO2e/year"},
            "scenario_kwh": {"low": scenario.low, "central": scenario.central, "high": scenario.high, "unit": "kg_CO2e/year"},
            "change_kwh": {"low": change_kwh.low, "central": change_kwh.central, "high": change_kwh.high, "unit": "kWh/year"},
        }
        method = "GH_HEAT_PUMP_SEASONAL_SPLIT_v1"
    else:
        baseline = Range.constant(annual_gas).multiply(gas_factor.factor_value)
        reduction_gas = Range.constant(heating_gas).multiply(insulation_reduction)
        scenario_gas = Range.constant(annual_gas).subtract(reduction_gas)
        scenario = scenario_gas.multiply(gas_factor.factor_value)
        reduction = baseline.subtract(scenario)
        energy = {
            "baseline_kwh": {"low": baseline.low, "central": baseline.central, "high": baseline.high, "unit": "kg_CO2e/year"},
            "scenario_kwh": {"low": scenario.low, "central": scenario.central, "high": scenario.high, "unit": "kg_CO2e/year"},
            "change_kwh": {"low": reduction_gas.low, "central": reduction_gas.central, "high": reduction_gas.high, "unit": "kWh/year"},
        }
        method = "GH_INSULATION_FRACTION_v1"

    co2e = ValueRange(low=reduction.low, central=reduction.central, high=reduction.high, unit="kg_CO2e/year")
    claim = co2e.central > 0
    flags: list[str] = []
    if reduction.central < 0:
        claim = False
        flags.append("SCENARIO_NOT_LOWER_THAN_BASELINE")
    if reduction.low < 0:
        flags.append("RANGE_INCLUDES_NO_REDUCTION")

    return ImpactResult(
        customer_id=customer_id,
        product=ProductId.GREEN_HOME,
        status=ImpactStatus.estimated,
        is_estimate=True,
        estimate_label=ESTIMATE_LABEL,
        claim_reduction=claim,
        impact_type="annual_home_energy_reduction",
        co2e=co2e,
        energy=energy,
        paper=None,
        digital_adoption=None,
        baseline=ValueRange(low=baseline.low, central=baseline.central, high=baseline.high, unit="kg_CO2e/year"),
        scenario=ValueRange(low=(baseline.subtract(reduction)).low, central=(baseline.subtract(reduction)).central, high=(baseline.subtract(reduction)).high, unit="kg_CO2e/year"),
        method=method,
        input_quality="FULL_12M" if len([v for v in gas_monthly if v is not None]) >= 12 else "ANNUALISED_PARTIAL",
        factor_ids=["GAS_NATURAL_GCV", "GRID_ELEC_UK"],
        factor_version=registry.factor_version,
        assumption_ids=["BOILER_EFFICIENCY", "HP_SCOP", "HEATING_REDUCTION_LOFT_WALL"],
        provenance_grade=registry.provenance_grade(["GAS_NATURAL_GCV", "GRID_ELEC_UK"]),
        assumptions=[
            "Hot-water and cooking are assumed to remain on gas",
            "Annual gas use is split into baseload and space-heating share",
        ],
        limitations=["Estimate, not a measured outcome"],
        reason_codes=[],
        cutoff_date=cutoff,
        calculated_at=datetime.now(timezone.utc),
        flags=flags,
    )
