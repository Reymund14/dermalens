from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models as M
from .config import settings
from .db import Base, SessionLocal, engine
from .routers import admin, auth, clinic, derm, patient, reference


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)  # PostgreSQL uses migrations/001_init.sql
    # BackgroundTasks do not survive a restart; free those sessions for resubmit.
    with SessionLocal() as db:
        db.query(M.CaptureSession).filter_by(status="processing").update(
            {"status": "failed", "error": "interrupted_by_restart"})
        db.commit()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="DermaLens API",
    version="0.1.0",
    description="Pre-screening, skincare information and referral API for ICONIC Aesthetic Clinic. "
                "Informational guidance only; not a medical diagnosis.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

for r in (auth.router, reference.router, patient.router, clinic.router, derm.router, admin.router):
    app.include_router(r, prefix="/api/v1")


@app.get("/health")
def health():
    return {"ok": True}
