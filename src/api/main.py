from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api import stubs

app = FastAPI(
    title="Megathon API",
    version="0.1.0",
    description="Backend server for Glass-Box Green Insights (stub data until the real pipeline is connected)",
)

ERROR_CODES = {400: "BAD_REQUEST", 404: "NOT_FOUND", 422: "VALIDATION_ERROR"}


@app.exception_handler(StarletteHTTPException)
async def http_error(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": str(exc.detail), "code": ERROR_CODES.get(exc.status_code, "INTERNAL_ERROR"), "detail": None},
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse(
        status_code=422,
        content={"error": "Invalid request", "code": "VALIDATION_ERROR", "detail": jsonable_encoder(exc.errors())},
    )


def page(items, limit, offset):
    return {"items": items[offset: offset + limit], "total": len(items), "limit": limit, "offset": offset}


def need_customer(customer_id):
    if customer_id not in stubs.CUSTOMERS:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")


# ---------- system ----------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"message": "Megathon API is running. See /docs"}


@app.get("/meta")
def meta():
    return stubs.meta()


# ---------- catalogue ----------
@app.get("/products")
def products():
    return {"items": stubs.PRODUCTS}


@app.get("/reason-codes")
def reason_codes():
    return {"items": stubs.REASON_CODES}


# ---------- customer view ----------
@app.get("/customers")
def customers(region: str | None = None, search: str | None = None,
              limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    return page(stubs.customer_list(region, search), limit, offset)


@app.get("/customers/{customer_id}")
def customer(customer_id: str):
    need_customer(customer_id)
    c = stubs.CUSTOMERS[customer_id]
    return {"customer_id": customer_id, "profile": c["profile"], "features": c["features"],
            "holdings": c["holdings"], "vehicle": c["vehicle"], "data_quality": c["data_quality"],
            "data_as_of": stubs.DATA_AS_OF}


@app.get("/customers/{customer_id}/opportunities")
def opportunities(customer_id: str):
    need_customer(customer_id)
    return {"items": stubs.visible(customer_id), "data_as_of": stubs.DATA_AS_OF}


@app.get("/customers/{customer_id}/opportunities/{product_id}")
def opportunity(customer_id: str, product_id: str):
    need_customer(customer_id)
    for o in stubs.OPPS[customer_id]:
        if o["product_id"] == product_id.upper():
            return o
    raise HTTPException(status_code=404, detail=f"{product_id} was not evaluated for {customer_id}")


@app.get("/customers/{customer_id}/audit")
def audit(customer_id: str):
    need_customer(customer_id)
    return {"items": stubs.OPPS[customer_id]}


# ---------- business dashboard ----------
@app.get("/business/summary")
def business_summary():
    return stubs.business_summary()


@app.get("/business/queue")
def business_queue(product_id: str | None = None, min_confidence: float = 0.0,
                   limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    return page(stubs.queue(product_id, min_confidence), limit, offset)
