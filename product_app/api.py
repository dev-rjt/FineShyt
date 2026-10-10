"""FastAPI backend for the submission-ready Verdant demo."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import time

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from api_service import bank_bootstrap, customer_profile, feature_weights, health_details, score_customer
from auth import Principal, authenticate, credentials_ready, load_local_env

load_local_env(Path(__file__).with_name(".env"))

app = FastAPI(
    title="Verdant Green Customer Insights API",
    version="1.0.0",
    description="Authenticated integration API for model, rules, impact, explanation and dashboard layers.",
)


class LoginRequest(BaseModel):
    username: str
    password: str


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
    profile = customer_profile(customer_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return profile


@app.get("/customers/{customer_id}/opportunities")
def get_opportunities(customer_id: str, principal: dict = Depends(current_principal)):
    allow_customer(customer_id, principal)
    if customer_profile(customer_id) is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    items, source = score_customer(customer_id)
    return {"items": items, "scoring_source": source}


@app.get("/bank/bootstrap")
def get_bank_bootstrap(_: dict = Depends(require_bank)):
    return bank_bootstrap()


@app.get("/bank/model/feature-weights/{product}")
def get_feature_weights(product: str, _: dict = Depends(require_bank)):
    try:
        return {"items": feature_weights(product)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown product") from exc
