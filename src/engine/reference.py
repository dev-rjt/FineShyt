"""Validation and lookup helpers for engine reference data.

The data layer owns persistence.  These lightweight views let the engine use
rows from SQLAlchemy, dictionaries, or CSV-derived records without coupling
the calculation code to a database client.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any


class MissingReferenceData(ValueError):
    """Raised internally when a required factor or assumption is unavailable."""

    def __init__(self, reference_id: str):
        super().__init__(reference_id)
        self.reference_id = reference_id


def _row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    if is_dataclass(row):
        return asdict(row)
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    return {key: value for key, value in vars(row).items() if not key.startswith("_")}


def _index(rows: Mapping[str, Any] | Iterable[Any], id_field: str) -> dict[str, dict[str, Any]]:
    if isinstance(rows, Mapping):
        indexed: dict[str, dict[str, Any]] = {}
        for key, value in rows.items():
            if isinstance(value, (int, float)):
                indexed[str(key)] = {id_field: str(key), "value": value}
            else:
                row = _row_dict(value)
                row.setdefault(id_field, str(key))
                indexed[str(row[id_field])] = row
        return indexed
    return {str(row[id_field]): row for item in rows for row in [_row_dict(item)]}


@dataclass(frozen=True)
class ReferenceData:
    """Read-only, validated view of factors and model assumptions."""

    factors: dict[str, dict[str, Any]]
    assumptions: dict[str, dict[str, Any]]

    @classmethod
    def from_rows(
        cls,
        factors: Mapping[str, Any] | Iterable[Any],
        assumptions: Mapping[str, Any] | Iterable[Any],
    ) -> "ReferenceData":
        return cls(_index(factors, "factor_id"), _index(assumptions, "id"))

    def factor_value(self, factor_id: str) -> float:
        try:
            row = self.factors[factor_id]
        except KeyError as exc:
            raise MissingReferenceData(factor_id) from exc
        value = row.get("kg_co2e_per_unit", row.get("factor_value", row.get("value")))
        if value is None:
            raise MissingReferenceData(factor_id)
        return float(value)

    def factor_payload(self, factor_id: str) -> dict[str, Any]:
        if factor_id not in self.factors:
            raise MissingReferenceData(factor_id)
        row = self.factors[factor_id]
        value = self.factor_value(factor_id)
        return {
            "factor_id": factor_id,
            "activity": row.get("activity"),
            "kg_co2e_per_unit": value,
            "unit": row.get("unit", row.get("activity_unit")),
            "source": row.get("source"),
            "source_year": row.get("source_year"),
        }

    def assumption_values(self, assumption_id: str) -> tuple[float, float, float]:
        try:
            row = self.assumptions[assumption_id]
        except KeyError as exc:
            raise MissingReferenceData(assumption_id) from exc

        central = row.get("central", row.get("value"))
        low = row.get("low", central)
        high = row.get("high", central)
        if low is None or central is None or high is None:
            raise MissingReferenceData(assumption_id)
        values = (float(low), float(central), float(high))
        if not values[0] <= values[1] <= values[2]:
            raise ValueError(f"Assumption {assumption_id} must satisfy low <= central <= high")
        return values

    def assumption_payload(self, assumption_id: str) -> dict[str, Any]:
        if assumption_id not in self.assumptions:
            raise MissingReferenceData(assumption_id)
        row = self.assumptions[assumption_id]
        _, central, _ = self.assumption_values(assumption_id)
        return {
            "id": assumption_id,
            "value": central,
            "unit": row.get("unit"),
            "source": row.get("source"),
        }
