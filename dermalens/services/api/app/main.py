from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import models as M
from .config import PRODUCTION, settings
from .db import Base, SessionLocal, engine
from .routers import account, admin, auth, clinic, derm, notifications, patient, reference

log = logging.getLogger("dermalens.api")
STARTED = time.time()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)  # PostgreSQL uses migrations/001_init.sql + 002_accounts.sql
    # BackgroundTasks do not survive a restart; free those sessions for resubmit.
    with SessionLocal() as db:
        db.query(M.CaptureSession).filter_by(status="processing").update(
            {"status": "failed", "error": "interrupted_by_restart"})
        db.commit()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="DermaLens API",
    version="0.2.0",
    description="Pre-screening, skincare information and referral API for ICONIC Aesthetic Clinic. "
                "Informational guidance only; not a medical diagnosis.",
)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}
DOCS = ("/docs", "/redoc", "/openapi.json")


@app.middleware("http")
async def harden(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    try:
        response = await call_next(request)
    except Exception:  # never leak a stack trace to the client
        log.exception("unhandled error, request %s %s %s", rid, request.method, request.url.path)
        response = JSONResponse({"detail": "something went wrong on our side; please try again",
                                 "request_id": rid}, status_code=500)
    response.headers.update(SECURITY_HEADERS)
    response.headers["X-Request-ID"] = rid
    if not request.url.path.startswith(DOCS):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"  # health data must not sit in shared caches
    if PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Retry-After", "X-Request-ID", "Content-Disposition"],
)

for r in (auth.router, account.router, reference.router, patient.router, clinic.router, derm.router,
          admin.router, notifications.router):
    app.include_router(r, prefix="/api/v1")


@app.get("/health")
def health():
    """For uptime monitors: 503 when the database is unreachable."""
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as e:
        log.error("health check: database unreachable: %s", e)
        return JSONResponse({"ok": False, "database": "unreachable"}, status_code=503)
    return {"ok": True, "database": "ok", "version": app.version, "uptime_s": int(time.time() - STARTED)}
