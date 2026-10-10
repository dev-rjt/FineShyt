from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from carbon_engine.schemas import EligibilityResult, ImpactResult, MLPayload, Opportunity, ProductId
from eligibility.engine import evaluate_eligibility
from carbon_engine.router import calculate_impact
from recommender.gate import InvalidMLPayload
from recommender.orchestrator import evaluate_opportunity, evaluate_customer_products, evaluate_business_view

app = FastAPI(title="Green Insights — Rules, Carbon & Recommender", version="0.1.0")


class EligibilityRequest(BaseModel):
    customer_ctx: dict[str, Any]
    product: ProductId
    run_date: Optional[date] = None
    mock: bool = False


class ImpactRequest(BaseModel):
    customer_ctx: dict[str, Any]
    product: ProductId
    eligibility_status: str = "ELIGIBLE"
    overrides: dict[str, Any] = Field(default_factory=dict)
    mock: bool = False


class OpportunityRequest(BaseModel):
    customer_ctx: dict[str, Any]
    ml_payload: dict[str, Any]
    product: ProductId
    p95_by_product: dict[str, float] = Field(default_factory=dict)
    run_date: Optional[date] = None
    mock: bool = False


class MultiProductRequest(BaseModel):
    customer_ctx: dict[str, Any]
    ml_by_product: dict[str, dict[str, Any]]
    p95_by_product: dict[str, float] = Field(default_factory=dict)
    run_date: Optional[date] = None
    mock: bool = False


MOCK_OPPORTUNITY = {
    "mock": True,
    "message": "Mock opportunity for parallel UI development",
}


@app.post("/eligibility/evaluate", response_model=EligibilityResult)
def post_eligibility(body: EligibilityRequest) -> EligibilityResult:
    if body.mock:
        raise HTTPException(status_code=501, detail="Use mock:false for real evaluation")
    return evaluate_eligibility(body.customer_ctx, body.product, run_date=body.run_date)


@app.post("/impact/calculate", response_model=ImpactResult)
def post_impact(body: ImpactRequest) -> ImpactResult:
    if body.mock:
        raise HTTPException(status_code=501, detail="Use mock:false for real calculation")
    from carbon_engine.schemas import EligibilityStatus

    try:
        status = EligibilityStatus(body.eligibility_status)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    result = calculate_impact(body.customer_ctx, body.product, status, overrides=body.overrides)
    return result


@app.post("/opportunities/evaluate", response_model=Opportunity)
def post_opportunity(body: OpportunityRequest) -> Opportunity:
    if body.mock:
        raise HTTPException(status_code=422, detail=MOCK_OPPORTUNITY)
    try:
        return evaluate_opportunity(
            body.customer_ctx,
            body.ml_payload,
            body.product,
            p95_by_product=body.p95_by_product,
            run_date=body.run_date,
        )
    except InvalidMLPayload as e:
        raise HTTPException(status_code=422, detail={"code": "INVALID_ML_PAYLOAD", "message": str(e)}) from e


@app.post("/recommendations/customer")
def post_customer_recommendations(body: MultiProductRequest) -> dict[str, Any]:
    if body.mock:
        return MOCK_OPPORTUNITY
    try:
        return evaluate_customer_products(
            body.customer_ctx,
            body.ml_by_product,
            p95_by_product=body.p95_by_product,
            run_date=body.run_date,
        ).model_dump()
    except InvalidMLPayload as e:
        raise HTTPException(status_code=422, detail={"code": "INVALID_ML_PAYLOAD", "message": str(e)}) from e


@app.post("/recommendations/business")
def post_business_recommendations(body: MultiProductRequest) -> dict[str, Any]:
    if body.mock:
        return MOCK_OPPORTUNITY
    try:
        return evaluate_business_view(
            body.customer_ctx,
            body.ml_by_product,
            p95_by_product=body.p95_by_product,
            run_date=body.run_date,
        ).model_dump()
    except InvalidMLPayload as e:
        raise HTTPException(status_code=422, detail={"code": "INVALID_ML_PAYLOAD", "message": str(e)}) from e
