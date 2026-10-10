from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from carbon_engine.factors import FactorRegistry, get_registry
from carbon_engine.ranges import Range
from carbon_engine.schemas import Co2eBlock, ImpactResult, ImpactStatus, ProductId, ValueRange

ROOT = Path(__file__).resolve().parent.parent
THRESHOLDS_PATH = ROOT / "config" / "thresholds.yaml"
ESTIMATE_LABEL = "Estimated potential impact, not a measured result"


def _load_thresholds() -> dict[str, Any]:
    with THRESHOLDS_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def calculate_paperless_impact(
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

    paper_statements = ctx.get("paper_statements")
    statements_per_year = ctx.get("statements_per_year")
    if statements_per_year is None:
        if paper_statements is True:
            statements_per_year = 12
        else:
            return ImpactResult(
                customer_id=customer_id,
                product=ProductId.PAPERLESS_BANKING,
                status=ImpactStatus.insufficient_data,
                is_estimate=True,
                estimate_label=ESTIMATE_LABEL,
                claim_reduction=False,
                reason_codes=["IMPACT_MISSING_STATEMENT_COUNT"],
                cutoff_date=cutoff,
                calculated_at=datetime.now(timezone.utc),
                factor_version=registry.factor_version,
            )

    statements = float(statements_per_year)
    sheets_per_statement = registry.assumption_range("SHEETS_PER_STATEMENT")
    sheet_mass = registry.assumption_range("SHEET_MASS_KG")
    if sheets_per_statement is None or sheet_mass is None:
        return ImpactResult(
            customer_id=customer_id,
            product=ProductId.PAPERLESS_BANKING,
            status=ImpactStatus.insufficient_data,
            is_estimate=True,
            estimate_label=ESTIMATE_LABEL,
            claim_reduction=False,
            reason_codes=["IMPACT_MISSING_FACTOR"],
            cutoff_date=cutoff,
            calculated_at=datetime.now(timezone.utc),
            factor_version=registry.factor_version,
        )

    statements_range = Range(statements, statements, statements)
    sheets_avoided = statements_range.multiply(sheets_per_statement)
    paper_kg = sheets_avoided.multiply(sheet_mass)

    enable_paper_co2e = bool(thresholds.get("enable_paper_co2e", False))
    if enable_paper_co2e:
        grid = registry.get_factor("GRID_ELEC_UK", geography=country, period=activity_year)
        if grid is None:
            co2e = Co2eBlock(status="not_reported", reason="NO_DOCUMENTED_METHOD")
        else:
            co2e = Co2eBlock(
                low=paper_kg.low * 0.0,
                central=paper_kg.central * 0.0,
                high=paper_kg.high * 0.0,
                unit="kg_CO2e/year",
                status="not_reported",
                reason="NO_DOCUMENTED_METHOD",
            )
    else:
        co2e = Co2eBlock(status="not_reported", reason="NO_DOCUMENTED_METHOD")

    digital_logins = ctx.get("digital_logins_90d")
    if digital_logins is None:
        digital_logins = 0
    digital_adoption = {
        "statements_moved_to_digital": {
            "low": statements_range.low,
            "central": statements_range.central,
            "high": statements_range.high,
            "unit": "statements/year",
        },
        "digital_logins_90d": digital_logins,
    }

    paper = {
        "statements_avoided": {
            "low": statements_range.low,
            "central": statements_range.central,
            "high": statements_range.high,
            "unit": "statements/year",
        },
        "sheets_avoided": {
            "low": sheets_avoided.low,
            "central": sheets_avoided.central,
            "high": sheets_avoided.high,
            "unit": "sheets/year",
        },
        "paper_kg_avoided": {
            "low": paper_kg.low,
            "central": paper_kg.central,
            "high": paper_kg.high,
            "unit": "kg/year",
        },
    }

    return ImpactResult(
        customer_id=customer_id,
        product=ProductId.PAPERLESS_BANKING,
        status=ImpactStatus.estimated,
        is_estimate=True,
        estimate_label=ESTIMATE_LABEL,
        claim_reduction=False,
        impact_type="paper_statements_avoided",
        co2e=co2e,
        energy=None,
        paper=paper,
        digital_adoption=digital_adoption,
        method="PAPER_STATEMENTS_TO_DIGITAL_v1",
        input_quality="FULL_12M" if statements_per_year is not None else "INSUFFICIENT",
        factor_ids=[],
        factor_version=registry.factor_version,
        assumption_ids=["SHEETS_PER_STATEMENT", "SHEET_MASS_KG"],
        provenance_grade="PROVISIONAL",
        assumptions=[
            "Statements avoided are treated as the number of statements moved to digital",
            "Paper mass is estimated from A4 80gsm sheets",
        ],
        limitations=["Estimate, not a measured outcome"],
        reason_codes=[],
        cutoff_date=cutoff,
        calculated_at=datetime.now(timezone.utc),
    )
