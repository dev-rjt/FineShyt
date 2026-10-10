from __future__ import annotations

from typing import Any, Optional

import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THRESHOLDS_PATH = ROOT / "config" / "thresholds.yaml"


def _mean_summer_gas(gas_monthly: list[Any]) -> Optional[float]:
    if not gas_monthly or len(gas_monthly) < 12:
        return None
    # Jun, Jul, Aug = indices 5,6,7 if Jan-first; use last 12 months Jun-Aug as months 6-8 from end
    # Spec: mean(Jun, Jul, Aug) — assume list is Jan..Dec of latest year
    months = [gas_monthly[5], gas_monthly[6], gas_monthly[7]]
    if any(m is None for m in months):
        return None
    return sum(float(m) for m in months) / 3.0


def annual_gas_kwh(ctx: dict[str, Any]) -> Optional[float]:
    gas = ctx.get("gas_kwh_monthly")
    if not gas:
        return None
    vals = [v for v in gas if v is not None]
    if len(vals) >= 12:
        return sum(float(v) for v in vals)
    if len(vals) >= 6:
        return sum(float(v) for v in vals) / len(vals) * 12
    return None


def heating_gas_kwh(ctx: dict[str, Any]) -> Optional[float]:
    annual = annual_gas_kwh(ctx)
    if annual is None:
        return None
    gas = ctx.get("gas_kwh_monthly")
    if not gas:
        return None
    baseload_monthly = _mean_summer_gas(gas)
    if baseload_monthly is None:
        return None
    baseload = baseload_monthly * 12
    return max(0.0, annual - baseload)


def select_green_home_intervention(ctx: dict[str, Any]) -> Optional[str]:
    with THRESHOLDS_PATH.open(encoding="utf-8") as fh:
        thr = yaml.safe_load(fh)
    gh_thr = thr.get("green_home", {})
    hp_min = gh_thr.get("heat_pump_min_heating_gas_kwh", 3000)
    ins_min = gh_thr.get("insulation_min_heating_gas_kwh", 1500)

    heating = heating_gas_kwh(ctx)
    if heating is None:
        return None

    heating_type = ctx.get("heating_type")
    insulation = ctx.get("insulation_status")

    if heating_type == "GAS_BOILER" and heating >= hp_min:
        return "HEAT_PUMP"
    if insulation in (None, "NONE", "PARTIAL") and heating >= ins_min:
        return "LOFT_AND_WALL_INSULATION"
    if heating_type == "HEAT_PUMP" and insulation == "FULL":
        return None
    return None
