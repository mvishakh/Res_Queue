import logging

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api.routes import admin, allocations, auth, menu, queue, tables
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.webhooks import whatsapp_webhook

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("smart_queue")

settings = get_settings()

app = FastAPI(
    title="Smart Queue API",
    version="1.0.0",
    description="Restaurant waiting list and automated FCFS + Table Matching allocation.",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Restaurant-Id"],
)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    errors = [
        {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"].removeprefix("Value error, ")}
        for e in exc.errors()
    ]
    message = errors[0]["message"] if errors else "Invalid request"
    return JSONResponse(
        status_code=422, content={"error": {"code": "validation_failed", "message": message, "details": {"errors": errors}}}
    )


@app.exception_handler(IntegrityError)
async def integrity_handler(_: Request, exc: IntegrityError):
    # Database constraints are the last line of defence (e.g. a concurrent duplicate
    # allocation). Report a conflict instead of a 500.
    logger.warning("Integrity error: %s", exc.orig)
    return JSONResponse(
        status_code=409,
        content={"error": {"code": "conflict", "message": "The change conflicts with the current state. Refresh and try again.", "details": {}}},
    )


api = APIRouter(prefix="/api")
for r in (auth.router, queue.router, tables.router, allocations.router, menu.router, menu.public_router, admin.router, whatsapp_webhook.router):
    api.include_router(r)


@api.get("/health", tags=["health"])
def health():
    with SessionLocal() as db:
        db.execute(text("select 1"))
    return {"status": "ok"}


app.include_router(api)
