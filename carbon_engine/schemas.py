from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ProductId(str, Enum):
    EV_FINANCE = "EV_FINANCE"
    GREEN_HOME = "GREEN_HOME"
    SOLAR_FINANCE = "SOLAR_FINANCE"
    PAPERLESS_BANKING = "PAPERLESS_BANKING"


class EligibilityStatus(str, Enum):
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    ELIGIBLE_WITH_CONDITIONS = "ELIGIBLE_WITH_CONDITIONS"
    ELIGIBLE = "ELIGIBLE"


class RuleOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    MISSING = "MISSING"
    CONDITION = "CONDITION"


class ImpactStatus(str, Enum):
    estimated = "estimated"
    insufficient_data = "insufficient_data"
    not_applicable = "not_applicable"
    calculation_error = "calculation_error"


class ValueRange(BaseModel):
    low: float
    central: float
    high: float
    unit: str


class Co2eBlock(BaseModel):
    low: Optional[float] = None
    central: Optional[float] = None
    high: Optional[float] = None
    unit: Optional[str] = None
    status: Optional[str] = None
    reason: Optional[str] = None


class RuleDecision(BaseModel):
    rule_id: str
    outcome: RuleOutcome
    code: str
    severity: str
    criteria_source: Optional[str] = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    rule_version: str
    condition_text: Optional[str] = None


class EligibilityResult(BaseModel):
    customer_id: str
    product: ProductId
    eligibility_status: EligibilityStatus
    conditions: list[str] = Field(default_factory=list)
    decisions: list[RuleDecision] = Field(default_factory=list)
    evaluated_at: datetime
    rule_version: str
    no_automated_customer_message: bool = False


class ImpactResult(BaseModel):
    customer_id: str
    product: ProductId
    status: ImpactStatus
    is_estimate: bool = True
    estimate_label: str = "Estimated potential impact, not a measured result"
    claim_reduction: bool = False
    impact_type: Optional[str] = None
    co2e: Optional[ValueRange | Co2eBlock] = None
    energy: Optional[dict[str, Any]] = None
    paper: Optional[dict[str, Any]] = None
    digital_adoption: Optional[dict[str, Any]] = None
    baseline: Optional[ValueRange] = None
    scenario: Optional[ValueRange] = None
    method: Optional[str] = None
    input_quality: Optional[str] = None
    factor_ids: list[str] = Field(default_factory=list)
    factor_version: Optional[str] = None
    assumption_ids: list[str] = Field(default_factory=list)
    provenance_grade: Optional[str] = None
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    cutoff_date: date
    calculated_at: datetime
    engine_version: str = "carbon_engine_0.1.0"
    flags: list[str] = Field(default_factory=list)


class GateResult(BaseModel):
    passed: bool
    codes: list[str] = Field(default_factory=list)
    present_to_customer: bool = False
    present_to_business: bool = False


class PriorityDetail(BaseModel):
    score: float
    impact_norm: float
    rank_within_customer: Optional[int] = None
    propensity: float
    confidence: float


class MLPayload(BaseModel):
    propensity: float
    confidence: float
    reason_codes: list[str] = Field(default_factory=list)
    model_version: str = "ml_v0"

    @field_validator("propensity", "confidence")
    @classmethod
    def in_unit_interval(cls, v: float) -> float:
        if not isinstance(v, (int, float)):
            raise ValueError("must be numeric")
        if v < 0 or v > 1:
            raise ValueError("must be in [0, 1]")
        return float(v)


class Opportunity(BaseModel):
    customer_id: str
    product: ProductId
    propensity: float
    confidence: float
    reason_codes: list[str]
    eligibility_result: EligibilityStatus
    eligibility_conditions: list[str] = Field(default_factory=list)
    decision_codes: list[str] = Field(default_factory=list)
    gate: GateResult
    impact: ImpactResult
    priority: PriorityDetail
    cutoff_date: date
    outcome_window_days: int
    data_timestamp: date
    model_version: str
    rule_version: str
    factor_version: Optional[str] = None
    audience: Optional[dict[str, Any]] = None


class CustomerRecommendations(BaseModel):
    """Ranked opportunities suitable for customer-facing channels."""

    customer_id: str
    primary: Optional[Opportunity] = None
    secondary: list[Opportunity] = Field(default_factory=list)
    cutoff_date: date
    outcome_window_days: int


class BusinessRecommendations(BaseModel):
    """Ranked opportunities for RM / business queue (includes gated-out audit hints)."""

    customer_id: str
    queue: list[Opportunity] = Field(default_factory=list)
    blocked: list[dict[str, Any]] = Field(default_factory=list)
    cutoff_date: date
