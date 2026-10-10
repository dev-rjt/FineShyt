"""Transparent product-rule screening.

These rules decide whether an opportunity should be suppressed.  They do not
make, approximate, or describe a regulated product eligibility decision.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


PRODUCT_IDS = {"GP01", "GP02", "GP03", "GP04"}
NOTE = "Subject to the institution's authorised eligibility checks"
RULE_VERSION = "v1"


def _failed(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _explicitly_false(value: Any) -> bool:
    """Handle API booleans and bool-like values read from pandas/SQL rows."""

    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"false", "0", "no"}
    try:
        return bool(value) is False
    except (TypeError, ValueError):
        return False


def evaluate_gate(product_id: str, inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate documented product rules and return the contract Gate shape."""

    product_id = product_id.upper()
    if product_id not in PRODUCT_IDS:
        raise ValueError(f"Unsupported product_id: {product_id}")

    failed_rules: list[dict[str, str]] = []
    fuel_type = inputs.get("fuel_type", inputs.get("vehicle_fuel_type"))
    home_owner = inputs.get("home_owner")

    if product_id == "GP01" and str(fuel_type).upper() == "ELECTRIC":
        failed_rules.append(_failed("ALREADY_EV_OWNER", "Customer already drives an electric vehicle"))
    if product_id in {"GP02", "GP03"} and _explicitly_false(home_owner):
        failed_rules.append(_failed("NOT_HOME_OWNER", "Customer is not a home owner"))

    return {
        "rule_pass": not failed_rules,
        "failed_rules": failed_rules,
        "rule_version": RULE_VERSION,
        "note": NOTE,
    }
