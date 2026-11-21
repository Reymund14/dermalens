"""Counts for the badges in the web app's sidebar. No patient details, only numbers."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models as M
from ..config import settings
from ..db import get_db
from ..security import current_user

router = APIRouter(tags=["notifications"])


def _route(r: M.ConsultationSummary) -> str | None:
    return (r.data.get("route") or {}).get("code")


@router.get("/notifications")
def notifications(user: M.User = Depends(current_user), db: Session = Depends(get_db)):
    out: dict = {"role": user.role, "email_verified": user.email_verified_at is not None}
    if user.role in ("clinic_staff", "admin", "dermatologist"):
        shared = db.query(M.ConsultationSummary).filter_by(shared_with="iconic_clinic").all()
        if user.role in ("clinic_staff", "admin"):
            new = [r for r in shared if r.follow_up_status == "new"]
            out["inbox_new"] = len(new)
            out["inbox_urgent"] = sum(1 for r in new if _route(r) == "urgent_care")
            out["inbox_unreviewed"] = sum(1 for r in shared if r.reviewed_at is None)
        if user.role == "dermatologist":
            mine = {v.summary_id for v in db.query(M.DermReview.summary_id).filter_by(reviewer_id=user.id)}
            todo = [r for r in shared if r.id not in mine]
            out["queue_todo"] = len(todo)
            out["queue_urgent"] = sum(1 for r in todo if _route(r) in ("urgent_care", "dermatologist"))
    if user.role == "admin":
        cutoff = date.today() - timedelta(days=settings.fda_reverify_days - 14)
        out["catalog_due"] = sum(1 for p in db.query(M.Product).filter_by(is_listed=True)
                                 if p.fda is None or p.fda.verified_on < cutoff)
        out["locked_accounts"] = sum(1 for u in db.query(M.User).filter(M.User.locked_until.isnot(None))
                                     if u.locked_until.replace(tzinfo=None) > M.now().replace(tzinfo=None))
        out["email_failures"] = db.query(M.EmailLog).filter_by(status="failed").count()
    if user.role == "patient":
        out["checks_in_progress"] = db.query(M.CaptureSession).filter(
            M.CaptureSession.user_id == user.id,
            M.CaptureSession.status.in_(("uploaded", "processing"))).count()
    return out
