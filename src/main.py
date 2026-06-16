import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

from config import settings
from routers import inventory, pricing, regional

app = FastAPI(
    title="Wakr Market Intelligence API",
    version="1.6.0-draft",
    description="REST API serving boat market intelligence data from the Wakr Data Lake.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(inventory.router)
app.include_router(pricing.router)
app.include_router(regional.router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Map FastAPI's 422 validation errors to the contract-specified 400 envelope."""
    errors = exc.errors()
    first = errors[0] if errors else {}
    field = ".".join(str(loc) for loc in first.get("loc", [])[1:]) or None
    msg = first.get("msg", "Invalid or missing parameter.")
    code = "MISSING_PARAM" if first.get("type") == "missing" else "INVALID_PARAM"
    return JSONResponse(
        status_code=400,
        content={"error": {"code": code, "message": msg, **({"field": field} if field else {})}},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        content = exc.detail
    else:
        content = {"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}}
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception for %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL", "message": "An unexpected error occurred."}},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
