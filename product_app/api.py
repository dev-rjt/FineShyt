"""FastAPI backend for the submission-ready Verdant demo."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import time

import pandas as pd

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from api_service import (
    bank_bootstrap, business_summary, canonical_opportunities, customer_360, customer_directory,
    customer_profile, customer_transactions, data_catalog, feature_weights, health_details,
    product_catalog, reason_catalog, repository, system_meta,
    score_snapshot,
)
from auth import Principal, authenticate, credentials_ready, load_local_env
from contract_adapter import contract_impact as estimate_impact
from config import PRODUCT_IDS
from txn_classifier import rule_classify

load_local_env(Path(__file__).with_name(".env"))

app = FastAPI(
    title="Verdant Green Customer Insights API",
    version="1.0.0",
    description="Authenticated integration API for model, rules, impact, explanation and dashboard layers.",
)

ERROR_CODES = {400: "BAD_REQUEST", 401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND", 422: "VALIDATION_ERROR"}


@app.exception_handler(StarletteHTTPException)
async def http_error(_, exc):
    return JSONResponse(status_code=exc.status_code, content={
        "error": str(exc.detail), "code": ERROR_CODES.get(exc.status_code, "INTERNAL_ERROR"), "detail": None,
    })


@app.exception_handler(RequestValidationError)
async def validation_error(_, exc):
    return JSONResponse(status_code=422, content={
        "error": "Invalid request", "code": "VALIDATION_ERROR", "detail": jsonable_encoder(exc.errors()),
    })


class LoginRequest(BaseModel):
    username: str
    password: str


class PayloadRequest(BaseModel):
    items: list[dict]


class ImpactRequest(BaseModel):
    product_id: str
    inputs: dict


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _secret() -> bytes:
    value = os.getenv("APP_SESSION_SECRET", "")
    if len(value) < 24:
        raise RuntimeError("APP_SESSION_SECRET must contain at least 24 characters")
    return value.encode("utf-8")


def issue_token(principal: Principal) -> str:
    payload = {
        "sub": principal.username,
        "role": principal.role,
        "display_name": principal.display_name,
        "customer_id": principal.customer_id,
        "exp": int(time.time()) + 12 * 60 * 60,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _b64(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def verify_token(token: str) -> dict:
    try:
        body, supplied = token.split(".", 1)
        expected = _b64(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(supplied, expected):
            raise ValueError("bad signature")
        payload = json.loads(_unb64(body))
        if int(payload["exp"]) < int(time.time()):
            raise ValueError("expired")
        return payload
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired session") from exc


def current_principal(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    return verify_token(authorization[7:])


def require_bank(principal: dict = Depends(current_principal)) -> dict:
    if principal["role"] != "bank":
        raise HTTPException(status_code=403, detail="Bank access required")
    return principal


def allow_customer(customer_id: str, principal: dict) -> None:
    if principal["role"] != "bank" and principal.get("customer_id") != customer_id:
        raise HTTPException(status_code=403, detail="This customer account cannot access another customer")


@app.get("/health")
def health():
    return health_details()


@app.get("/")
def root():
    return {"message": "Verdant Green Customer Insights API", "docs": "/docs", "health": "/health"}


@app.get("/meta")
def meta(_: dict = Depends(current_principal)):
    return system_meta()


@app.get("/products")
def products(_: dict = Depends(current_principal)):
    return {"items": product_catalog()}


@app.get("/reason-codes")
def reason_codes(_: dict = Depends(current_principal)):
    return {"items": reason_catalog()}


@app.get("/emission-factors")
def emission_factors(_: dict = Depends(current_principal)):
    return {"items": bank_bootstrap()["emission_factors"]}


@app.post("/categorise")
def categorise(request: PayloadRequest, _: dict = Depends(require_bank)):
    items = []
    for source in request.items:
        description = str(source.get("merchant_description") or "")
        category = rule_classify(description).upper().replace(" ", "_")
        items.append({"merchant_description": description, "category": category,
                      "method": "RULE", "confidence": 1.0, "model_version": "ordered-rules-v1"})
    return {"items": items}


@app.post("/impact/estimate")
def impact_estimate(request: ImpactRequest, _: dict = Depends(require_bank)):
    reverse = {value: key for key, value in PRODUCT_IDS.items()}
    product = reverse.get(request.product_id.upper())
    if product is None:
        raise HTTPException(status_code=404, detail="Unknown product")
    values = dict(request.inputs)
    if "fuel_type" in values and "fuel_type_code" not in values:
        values["fuel_type_code"] = {"PETROL": 0, "DIESEL": 1, "HYBRID": 2, "ELECTRIC": 3}.get(str(values["fuel_type"]).upper())
    if "electricity_kwh_12m" in values:
        values["elec_kwh_yr"] = values["electricity_kwh_12m"]
    if "gas_kwh_12m" in values:
        values["gas_kwh_yr"] = values["gas_kwh_12m"]
    impact = estimate_impact(product, pd.Series(values))
    return {key: impact[key] for key in ["status", "is_estimate", "horizon_months", "method", "metrics", "assumptions", "factors", "missing_inputs"]}


@app.post("/score")
def score(payload: dict, _: dict = Depends(require_bank)):
    return score_snapshot(payload)


@app.post("/auth/login")
def login(request: LoginRequest):
    if not credentials_ready():
        raise HTTPException(status_code=503, detail="Demo credentials are not configured")
    principal = authenticate(request.username, request.password)
    if principal is None:
        raise HTTPException(status_code=401, detail="Invalid user ID or password")
    return {
        "access_token": issue_token(principal),
        "token_type": "bearer",
        "principal": {
            "username": principal.username,
            "role": principal.role,
            "display_name": principal.display_name,
            "customer_id": principal.customer_id,
        },
    }


@app.get("/me")
def me(principal: dict = Depends(current_principal)):
    return principal


@app.get("/customers/{customer_id}")
def get_customer(customer_id: str, principal: dict = Depends(current_principal)):
    allow_customer(customer_id, principal)
    profile = customer_360(customer_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return profile


@app.get("/customers")
def get_customers(
    region: str | None = None, search: str | None = None,
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
    _: dict = Depends(require_bank),
):
    rows = customer_directory()
    if region:
        rows = [row for row in rows if str(row["region"]).casefold() == region.casefold()]
    if search:
        rows = [row for row in rows if row["customer_id"].casefold().startswith(search.casefold())]
    return {"items": rows[offset:offset + limit], "total": len(rows), "limit": limit, "offset": offset}


@app.get("/customers/{customer_id}/transactions")
def get_transactions(
    customer_id: str, category: str | None = None,
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
    principal: dict = Depends(current_principal),
):
    allow_customer(customer_id, principal)
    if customer_profile(customer_id) is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    rows = customer_transactions(customer_id)
    if category:
        rows = [row for row in rows if row["category"] == category.upper()]
    return {"items": rows[offset:offset + limit], "total": len(rows), "limit": limit, "offset": offset}


@app.get("/customers/{customer_id}/opportunities")
def get_opportunities(customer_id: str, principal: dict = Depends(current_principal)):
    allow_customer(customer_id, principal)
    if customer_profile(customer_id) is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    items, source = canonical_opportunities(customer_id, include_suppressed=False)
    return {"items": items, "data_as_of": items[0]["data_as_of"] if items else None, "scoring_source": source}


@app.get("/customers/{customer_id}/audit")
def get_customer_audit(customer_id: str, _: dict = Depends(require_bank)):
    if customer_profile(customer_id) is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    items, source = canonical_opportunities(customer_id, include_suppressed=True)
    return {"items": items, "scoring_source": source}


@app.get("/customers/{customer_id}/opportunities/{product_id}")
def get_opportunity(product_id: str, customer_id: str, principal: dict = Depends(current_principal)):
    allow_customer(customer_id, principal)
    if customer_profile(customer_id) is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    include_suppressed = principal["role"] == "bank"
    items, _ = canonical_opportunities(customer_id, include_suppressed=include_suppressed)
    match = next((item for item in items if item["product_id"] == product_id.upper()), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Opportunity is not available")
    return match


@app.get("/bank/bootstrap")
def get_bank_bootstrap(_: dict = Depends(require_bank)):
    return bank_bootstrap()


@app.get("/bank/model/feature-weights/{product}")
def get_feature_weights(product: str, _: dict = Depends(require_bank)):
    try:
        return {"items": feature_weights(product)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown product") from exc


@app.get("/bank/data-catalog")
def get_data_catalog(_: dict = Depends(require_bank)):
    return data_catalog()


@app.get("/evaluation")
def get_evaluation(_: dict = Depends(require_bank)):
    report = repository()["evaluation"]
    return {"items": [{"component": product, "split": "test", "metrics": values["test"],
                        "baseline": values["baseline_logreg_test"]}
                       for product, values in report.items() if product in PRODUCT_IDS]}


@app.get("/business/summary")
def get_business_summary(_: dict = Depends(require_bank)):
    return business_summary()
