from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from carbon_engine.ranges import Range

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FACTORS_PATH = ROOT / "data" / "emissions_factors.csv"
DEFAULT_ASSUMPTIONS_PATH = ROOT / "data" / "assumptions.csv"


@dataclass(frozen=True)
class EmissionFactor:
    factor_id: str
    factor_value: float
    factor_unit: str
    activity_unit: str
    geography: str
    period: str
    version: str
    boundary: str
    verification_status: str
    source_name: str


@dataclass(frozen=True)
class Assumption:
    assumption_id: str
    low: float
    central: float
    high: float
    unit: str
    status: str
    source_name: str


class FactorRegistry:
    def __init__(
        self,
        factors_path: Path = DEFAULT_FACTORS_PATH,
        assumptions_path: Path = DEFAULT_ASSUMPTIONS_PATH,
    ) -> None:
        self._factors_path = factors_path
        self._assumptions_path = assumptions_path
        self._factors: dict[str, EmissionFactor] = {}
        self._assumptions: dict[str, Assumption] = {}
        self._factor_version: str = ""
        self.reload()

    def reload(self) -> None:
        self._factors = _load_factors(self._factors_path)
        self._assumptions = _load_assumptions(self._assumptions_path)
        digest = hashlib.sha256(
            (self._factors_path.read_bytes() + self._assumptions_path.read_bytes())
        ).hexdigest()[:12]
        self._factor_version = f"ef-register-2026-{digest}"

    @property
    def factor_version(self) -> str:
        return self._factor_version

    def get_factor(
        self, factor_id: str, geography: str = "GB", period: str = "2026"
    ) -> Optional[EmissionFactor]:
        f = self._factors.get(factor_id)
        if f is None:
            return None
        if f.geography != geography:
            return None
        if f.period != period:
            return None
        return f

    def get_assumption(self, assumption_id: str) -> Optional[Assumption]:
        return self._assumptions.get(assumption_id)

    def assumption_range(self, assumption_id: str) -> Optional[Range]:
        a = self.get_assumption(assumption_id)
        if a is None:
            return None
        return Range(a.low, a.central, a.high)

    def provenance_grade(self, factor_ids: list[str]) -> str:
        statuses = []
        for fid in factor_ids:
            f = self._factors.get(fid)
            if f:
                statuses.append(f.verification_status)
        if not statuses:
            return "PROVISIONAL"
        if all(s == "VERIFIED_OFFICIAL" for s in statuses):
            return "REPORTABLE"
        return "PROVISIONAL"


def _load_factors(path: Path) -> dict[str, EmissionFactor]:
    if not path.exists():
        raise FileNotFoundError(path)
    by_id: dict[str, list[EmissionFactor]] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            required = ["factor_value", "factor_unit", "source_name", "geography"]
            if any(not row.get(k) for k in required):
                continue
            ef = EmissionFactor(
                factor_id=row["factor_id"],
                factor_value=float(row["factor_value"]),
                factor_unit=row["factor_unit"],
                activity_unit=row["activity_unit"],
                geography=row["geography"],
                period=row["period"],
                version=row["version"],
                boundary=row.get("boundary", "UNCONFIRMED"),
                verification_status=row["verification_status"],
                source_name=row["source_name"],
            )
            by_id.setdefault(ef.factor_id, []).append(ef)
    result: dict[str, EmissionFactor] = {}
    for fid, rows in by_id.items():
        rows.sort(key=lambda r: r.version, reverse=True)
        result[fid] = rows[0]
    return result


def _load_assumptions(path: Path) -> dict[str, Assumption]:
    if not path.exists():
        raise FileNotFoundError(path)
    result: dict[str, Assumption] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            result[row["assumption_id"]] = Assumption(
                assumption_id=row["assumption_id"],
                low=float(row["low"]),
                central=float(row["central"]),
                high=float(row["high"]),
                unit=row["unit"],
                status=row["status"],
                source_name=row["source_name"],
            )
    return result


_default_registry: Optional[FactorRegistry] = None


def get_registry() -> FactorRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = FactorRegistry()
    return _default_registry
