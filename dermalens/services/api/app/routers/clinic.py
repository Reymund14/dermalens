"""Staff-facing endpoints. Every read of a summary is written to the audit log."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .. import models as M
from .. import storage
from ..db import get_db
from ..pipeline import current_images
from ..schemas import ReviewIn
from ..security import audit, now, require, sha256_hex

router = APIRouter(prefix="/clinic", tags=["clinic"])
staff = require("clinic_staff", "dermatologist", "admin")


def _live(row: M.ConsultationSummary | None) -> M.ConsultationSummary:
    if row is None or row.shared_with != "iconic_clinic":
        raise HTTPException(404, "summary not found")
    exp = row.expires_at
    if exp is not None and (exp if exp.tzinfo else exp.replace(tzinfo=now().tzinfo)) < now():
        raise HTTPException(410, "share link expired")
    return row


def _brief(r: M.ConsultationSummary) -> dict:
    return {"summary_id": str(r.id), "created_at": r.created_at.isoformat(),
            "route": (r.data.get("route") or {}).get("code"), "patient": r.data.get("patient"),
            "reviewed": r.reviewed_at is not None, "follow_up_status": r.follow_up_status,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None}


def _full(db: Session, r: M.ConsultationSummary) -> dict:
    reviewer = db.get(M.User, r.reviewed_by) if r.reviewed_by else None
    session = db.get(M.CaptureSession, r.session_id)
    views = sorted(current_images(session)) if session else []
    return {**_brief(r), "data": r.data, "staff_note": r.staff_note, "views": views,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
            "reviewed_by": (reviewer.display_name or reviewer.email) if reviewer else None}


@router.get("/summaries")
def list_summaries(route: str | None = None, reviewed: bool | None = None, follow_up: str | None = None,
                   user: M.User = Depends(staff), db: Session = Depends(get_db)):
    q = db.query(M.ConsultationSummary).filter_by(shared_with="iconic_clinic").order_by(
        M.ConsultationSummary.created_at.desc())
    out = []
    for r in q.limit(200):
        if route and (r.data.get("route") or {}).get("code") != route:
            continue
        if reviewed is not None and (r.reviewed_at is not None) != reviewed:
            continue
        if follow_up and r.follow_up_status != follow_up:
            continue
        out.append(_brief(r))
    return out


@router.get("/summaries/{summary_id}")
def get_summary(summary_id: str, request: Request, user: M.User = Depends(staff), db: Session = Depends(get_db)):
    row = _live(db.get(M.ConsultationSummary, uuid.UUID(summary_id)))
    audit(db, user, "view_summary", "consultation_summary", row.id, request)
    db.commit()
    return _full(db, row)


@router.get("/summaries/{summary_id}/pdf")
def get_summary_pdf(summary_id: str, request: Request, user: M.User = Depends(staff), db: Session = Depends(get_db)):
    row = _live(db.get(M.ConsultationSummary, uuid.UUID(summary_id)))
    audit(db, user, "view_summary_pdf", "consultation_summary", row.id, request)
    db.commit()
    return Response(storage.get(row.pdf_object_key), media_type="application/pdf")


@router.get("/s/{token}")
def open_share_link(token: str, request: Request, user: M.User = Depends(staff), db: Session = Depends(get_db)):
    """QR-code target: opens the summary only after staff log in."""
    row = _live(db.query(M.ConsultationSummary).filter_by(share_token_hash=sha256_hex(token)).one_or_none())
    audit(db, user, "view_summary_qr", "consultation_summary", row.id, request)
    db.commit()
    return _full(db, row)


@router.patch("/summaries/{summary_id}")
def review_summary(summary_id: str, body: ReviewIn, request: Request, user: M.User = Depends(staff),
                   db: Session = Depends(get_db)):
    row = _live(db.get(M.ConsultationSummary, uuid.UUID(summary_id)))
    if body.reviewed is not None:
        row.reviewed_by, row.reviewed_at = (user.id, now()) if body.reviewed else (None, None)
    if body.staff_note is not None:
        row.staff_note = body.staff_note
    if body.follow_up_status is not None:
        row.follow_up_status = body.follow_up_status
    audit(db, user, "review_summary", "consultation_summary", row.id, request,
          body.model_dump(exclude_none=True, exclude={"staff_note"}))
    db.commit()
    return _full(db, row)


@router.get("/summaries/{summary_id}/images/{view}")
def summary_image(summary_id: str, view: str, request: Request, user: M.User = Depends(staff),
                  db: Session = Depends(get_db)):
    """Photos of a shared case. Patients chose to share these with the clinic."""
    row = _live(db.get(M.ConsultationSummary, uuid.UUID(summary_id)))
    img = current_images(db.get(M.CaptureSession, row.session_id)).get(view)
    if img is None or img.object_key == "purged":
        raise HTTPException(404, "no image")
    audit(db, user, "view_summary_image", "consultation_summary", row.id, request, {"view": view})
    db.commit()
    return Response(storage.get(img.object_key), media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})
