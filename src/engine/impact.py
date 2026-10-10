"""Deterministic sustainability impact calculations for GP01--GP04."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any, Callable

from .reference import MissingReferenceData, ReferenceData


HORIZON_MONTHS = 12
KM_PER_MILE = 1.609344  # Exact unit conversion, not a modelling assumption.

METHODS = {
    "GP01": "EV_AVOIDED_V1: current fuel emissions minus electricity emissions after switching",
    "GP02": "HOME_EFFICIENCY_V1: energy saved by efficiency upgrades against current use",
    "GP03": "SOLAR_GENERATION_V1: electricity generated on site against current grid use",
    "GP04": "PAPER_AVOIDED_V1: paper statements replaced by digital statements",
}

FACTOR_IDS = {
    "PETROL": "UK_PETROL_2026",
    "DIESEL": "UK_DIESEL_2026",
    "GRID": "UK_GRID_ELECTRICITY_2026",
    "GAS": "UK_NATURAL_GAS_2026",
}


def _missing(product_id: str, missing: Iterable[str]) -> dict[str, Any]:
    return {
        "status": "INSUFFICIENT_DATA",
        "is_estimate": True,
        "horizon_months": HORIZON_MONTHS,
        "method": METHODS[product_id],
        "metrics": [],
        "assumptions": [],
        "factors": [],
        "missing_inputs": sorted(set(missing)),
    }


def _number(inputs: Mapping[str, Any], *names: str) -> float | None:
    for name in names:
        value = inputs.get(name)
        if value is not None:
            try:
                result = float(value)
            except (TypeError, ValueError):
                return None
            return result if math.isfinite(result) and result >= 0 else None
    return None


def _annual_energy(inputs: Mapping[str, Any], annual: str, monthly: str) -> float | None:
    value = _number(inputs, annual)
    if value is not None:
        return value
    value = _number(inputs, monthly)
    return value * HORIZON_MONTHS if value is not None else None


def _metric(metric: str, unit: str, values: Iterable[float]) -> dict[str, Any]:
    low, central, high = sorted(max(0.0, float(value)) for value in values)
    return {
        "metric": metric,
        "unit": unit,
        "low": round(low, 2),
        "central": round(central, 2),
        "high": round(high, 2),
    }


def _ok(
    product_id: str,
    metrics: list[dict[str, Any]],
    refs: ReferenceData,
    assumption_ids: Iterable[str],
    factor_ids: Iterable[str],
) -> dict[str, Any]:
    return {
        "status": "OK",
        "is_estimate": True,
        "horizon_months": HORIZON_MONTHS,
        "method": METHODS[product_id],
        "metrics": metrics,
        "assumptions": [refs.assumption_payload(key) for key in assumption_ids],
        "factors": [refs.factor_payload(key) for key in factor_ids],
        "missing_inputs": [],
    }


def _ev(inputs: Mapping[str, Any], refs: ReferenceData) -> dict[str, Any]:
    mileage = _number(inputs, "annual_mileage")
    fuel_type = str(inputs.get("fuel_type", inputs.get("vehicle_fuel_type", ""))).upper()
    missing = []
    if mileage is None:
        missing.append("annual_mileage")
    if fuel_type not in {"PETROL", "DIESEL", "HYBRID"}:
        missing.append("fuel_type")
    if missing:
        return _missing("GP01", missing)

    combustion = "PETROL" if fuel_type == "HYBRID" else fuel_type
    efficiency_id = f"A_{fuel_type}_L_PER_100KM"
    fuel_factor_id = FACTOR_IDS[combustion]
    fuel_efficiency = refs.assumption_values(efficiency_id)
    ev_intensity = refs.assumption_values("A_EV_KWH_PER_KM")
    fuel_factor = refs.factor_value(fuel_factor_id)
    grid_factor = refs.factor_value(FACTOR_IDS["GRID"])
    annual_km = mileage * KM_PER_MILE

    # Conservative bound pairs efficient combustion with a less efficient EV;
    # the upper bound pairs the opposite extremes. The central estimate uses
    # the two central values.
    avoided = [
        annual_km * fuel_efficiency[0] / 100 * fuel_factor - annual_km * ev_intensity[2] * grid_factor,
        annual_km * fuel_efficiency[1] / 100 * fuel_factor - annual_km * ev_intensity[1] * grid_factor,
        annual_km * fuel_efficiency[2] / 100 * fuel_factor - annual_km * ev_intensity[0] * grid_factor,
    ]
    return _ok(
        "GP01",
        [_metric("CO2E_KG", "kg CO2e per year", avoided)],
        refs,
        [efficiency_id, "A_EV_KWH_PER_KM"],
        [fuel_factor_id, FACTOR_IDS["GRID"]],
    )


def _home(inputs: Mapping[str, Any], refs: ReferenceData) -> dict[str, Any]:
    electricity = _annual_energy(inputs, "electricity_kwh_12m", "average_monthly_electricity_kwh")
    gas = _annual_energy(inputs, "gas_kwh_12m", "average_monthly_gas_kwh")
    missing = []
    if electricity is None:
        missing.append("electricity_kwh_12m")
    if gas is None:
        missing.append("gas_kwh_12m")
    if missing:
        return _missing("GP02", missing)

    electricity_reduction = refs.assumption_values("A_HOME_ELECTRICITY_REDUCTION")
    gas_reduction = refs.assumption_values("A_HOME_GAS_REDUCTION")
    grid_factor = refs.factor_value(FACTOR_IDS["GRID"])
    gas_factor = refs.factor_value(FACTOR_IDS["GAS"])
    energy_saved = [electricity * e + gas * g for e, g in zip(electricity_reduction, gas_reduction)]
    co2e_saved = [
        electricity * e * grid_factor + gas * g * gas_factor
        for e, g in zip(electricity_reduction, gas_reduction)
    ]
    return _ok(
        "GP02",
        [
            _metric("ENERGY_KWH", "kWh per year", energy_saved),
            _metric("CO2E_KG", "kg CO2e per year", co2e_saved),
        ],
        refs,
        ["A_HOME_ELECTRICITY_REDUCTION", "A_HOME_GAS_REDUCTION"],
        [FACTOR_IDS["GRID"], FACTOR_IDS["GAS"]],
    )


def _solar(inputs: Mapping[str, Any], refs: ReferenceData) -> dict[str, Any]:
    electricity = _annual_energy(inputs, "electricity_kwh_12m", "average_monthly_electricity_kwh")
    if electricity is None:
        return _missing("GP03", ["electricity_kwh_12m"])

    system_size = _number(inputs, "solar_system_kwp")
    size_assumption = system_size is None
    sizes = refs.assumption_values("A_SOLAR_SYSTEM_KWP") if size_assumption else (system_size,) * 3
    yields = refs.assumption_values("A_SOLAR_YIELD_KWH_PER_KWP")
    generation = [min(electricity, size * annual_yield) for size, annual_yield in zip(sizes, yields)]
    grid_factor = refs.factor_value(FACTOR_IDS["GRID"])
    assumptions = ["A_SOLAR_YIELD_KWH_PER_KWP"]
    if size_assumption:
        assumptions.insert(0, "A_SOLAR_SYSTEM_KWP")
    return _ok(
        "GP03",
        [
            _metric("ENERGY_KWH", "kWh per year", generation),
            _metric("CO2E_KG", "kg CO2e per year", [value * grid_factor for value in generation]),
        ],
        refs,
        assumptions,
        [FACTOR_IDS["GRID"]],
    )


def _paperless(inputs: Mapping[str, Any], refs: ReferenceData) -> dict[str, Any]:
    statements = _number(inputs, "paper_statements_12m")
    statement_assumption = False
    if statements is None and inputs.get("paper_statements_active") in {True, 1, "1", "true", "True"}:
        statements = refs.assumption_values("A_PAPER_STATEMENTS_PER_YEAR")[1]
        statement_assumption = True
    if statements is None:
        return _missing("GP04", ["paper_statements_12m"])

    sheets = refs.assumption_values("A_PAPER_SHEETS_PER_STATEMENT")
    paper_avoided = [statements * value for value in sheets]
    paper_ratio = _number(inputs, "paper_statement_ratio")
    digital_shift = min(100.0, paper_ratio * 100.0) if paper_ratio is not None else None
    metrics = [_metric("PAPER_SHEETS", "sheets per year", paper_avoided)]
    if digital_shift is not None:
        metrics.append(_metric("DIGITAL_ADOPTION_PP", "percentage points", [digital_shift] * 3))
    assumptions = ["A_PAPER_SHEETS_PER_STATEMENT"]
    if statement_assumption:
        assumptions.insert(0, "A_PAPER_STATEMENTS_PER_YEAR")
    return _ok("GP04", metrics, refs, assumptions, [])


CALCULATORS: dict[str, Callable[[Mapping[str, Any], ReferenceData], dict[str, Any]]] = {
    "GP01": _ev,
    "GP02": _home,
    "GP03": _solar,
    "GP04": _paperless,
}


def estimate_impact(
    product_id: str,
    inputs: Mapping[str, Any],
    *,
    factors: Mapping[str, Any] | Iterable[Any],
    assumptions: Mapping[str, Any] | Iterable[Any],
) -> dict[str, Any]:
    """Estimate impact using caller-supplied, versioned reference records.

    Missing inputs or reference rows produce the contract's
    ``INSUFFICIENT_DATA`` result. Invalid assumption ranges are configuration
    errors and intentionally raise ``ValueError`` rather than hiding bad data.
    """

    product_id = product_id.upper()
    if product_id not in CALCULATORS:
        raise ValueError(f"Unsupported product_id: {product_id}")
    refs = ReferenceData.from_rows(factors, assumptions)
    try:
        return CALCULATORS[product_id](inputs, refs)
    except MissingReferenceData as exc:
        return _missing(product_id, [f"reference:{exc.reference_id}"])
