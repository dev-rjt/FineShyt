from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

SUPPORTED_DISTANCE_UNITS = {"km", "mile"}
SUPPORTED_ENERGY_UNITS = {"kWh", "Wh", "MWh"}

MILE_TO_KM = 1.609344


@dataclass
class UnitConversionError(Exception):
    code: str
    message: str


def convert_distance_to_km(value: float, unit: str) -> float:
    u = unit.strip().lower()
    if u == "km":
        return value
    if u == "mile":
        return value * MILE_TO_KM
    raise UnitConversionError("UNSUPPORTED_UNIT", f"Unsupported distance unit: {unit}")


def convert_energy_to_kwh(value: float, unit: str) -> float:
    u = unit.strip()
    if u == "kWh":
        return value
    if u == "Wh":
        return value / 1000.0
    if u == "MWh":
        return value * 1000.0
    raise UnitConversionError("UNSUPPORTED_UNIT", f"Unsupported energy unit: {unit}")
