from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from dermalens_inference.quality import check, strip_exif

from .. import models as M
from .. import storage
from ..config import settings
from ..db import get_db
from ..pipeline import REQUIRED_VIEWS, current_images, process_session
from ..present import session_result
from ..schemas import ConsentIn, ImageIn, IntakeIn, ProfileIn, SessionIn, SummaryIn
from ..security import audit, decrypt, encrypt, now, require, sha256_hex, sign_upload, verify_upload
from ..summary import build_data, render_pdf

router = APIRouter(tags=["patient"])
patient = require("patient")


def latest_consents(db: Session, user_id) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for c in db.query(M.Consent).filter_by(user_id=user_id).order_by(M.Consent.recorded_at):
        out[c.purpose] = c.granted
    return out


def own_session(db: Session, user: M.User, session_id: str) -> M.CaptureSession:
    try:
        s = db.get(M.CaptureSession, uuid.UUID(session_id))
    except ValueError:
        s = None
    if s is None or s.user_id != user.id:
        raise HTTPException(404, "session not found")
    return s


# ----- Consent and profile ----------------------------------------------------

@router.post("/consents", status_code=201)
def record_consent(body: ConsentIn, request: Request, user: M.User = Depends(patient), db: Session = Depends(get_db)):
    if body.purpose == "service" and not body.granted:
        raise HTTPException(422, "withdrawing service consent means deleting the account: use DELETE /me")
    db.add(M.Consent(user_id=user.id, purpose=body.purpose, policy_version=settings.policy_version,
                     granted=body.granted))
    audit(db, user, "consent", "consent", body.purpose, request, {"granted": body.granted})
    db.commit()
    return latest_consents(db, user.id)


@router.get("/consents")
def get_consents(user: M.User = Depends(patient), db: Session = Depends(get_db)):
    return latest_consents(db, user.id)


@router.get("/me/profile")
def get_profile(user: M.User = Depends(patient), db: Session = Depends(get_db)):
    p = db.get(M.PatientProfile, user.id)
    if p is None:
        return None
    return {"full_name": decrypt(p.full_name_enc), "birth_year": p.birth_year, "sex_at_birth": p.sex_at_birth,
            "self_fitzpatrick": p.self_fitzpatrick, "skin_type": p.skin_type,
            "is_pregnant_or_breastfeeding": p.is_pregnant_or_breastfeeding}


@router.put("/me/profile")
def put_profile(body: ProfileIn, user: M.User = Depends(patient), db: Session = Depends(get_db)):
    p = db.get(M.PatientProfile, user.id) or M.PatientProfile(user_id=user.id, full_name_enc=b"")
    p.full_name_enc = encrypt(body.full_name)
    for k in ("birth_year", "sex_at_birth", "self_fitzpatrick", "skin_type", "is_pregnant_or_breastfeeding"):
        setattr(p, k, getattr(body, k))
    db.merge(p)
    db.commit()
    return get_profile(user, db)


# ----- Intake -----------------------------------------------------------------

@router.post("/intakes", status_code=201)
def create_intake(body: IntakeIn, user: M.User = Depends(patient), db: Session = Depends(get_db)):
    defs = {f.code: f for f in db.query(M.RedFlagDefinition)}
    missing = set(defs) - set(body.red_flags)
    unknown = set(body.red_flags) - set(defs)
    if missing or unknown:
        raise HTTPException(422, {"missing_red_flags": sorted(missing), "unknown_red_flags": sorted(unknown)})
    concern_codes = {c.code for c in db.query(M.Concern)}
    for c in body.concerns:
        if c.code not in concern_codes:
            raise HTTPException(422, f"unknown concern {c.code}")

    row = M.IntakeRow(user_id=user.id, questionnaire_version=settings.questionnaire_version,
                      on_isotretinoin=body.on_isotretinoin, current_rx_topicals=body.current_rx_topicals,
                      uses_actives_without_reaction=body.uses_actives_without_reaction,
                      free_text_enc=encrypt(body.free_text), **body.lifestyle.model_dump())
    row.concerns = [M.IntakeConcern(concern_code=c.code, self_severity=c.self_severity,
                                    duration_weeks=c.duration_weeks) for c in body.concerns]
    row.red_flags = [M.IntakeRedFlag(red_flag_code=k, answer=v) for k, v in sorted(body.red_flags.items())]
    for r in body.current_routine:
        if r.product_id and not db.get(M.Product, r.product_id):
            raise HTTPException(422, f"unknown product {r.product_id}")
    row.routine_items = [M.CurrentRoutineItem(**r.model_dump()) for r in body.current_routine]

    # Allergies belong to the person, not the intake: replace the declared list.
    db.query(M.UserAllergen).filter_by(user_id=user.id).delete()
    for a in body.allergens:
        if a.ingredient_id and not db.get(M.Ingredient, a.ingredient_id):
            raise HTTPException(422, f"unknown ingredient {a.ingredient_id}")
        if a.family_code and not db.get(M.IngredientFamily, a.family_code):
            raise HTTPException(422, f"unknown family {a.family_code}")
        if not (a.ingredient_id or a.family_code or a.raw_text):
            continue
        db.add(M.UserAllergen(user_id=user.id, **a.model_dump()))
    db.add(row)
    db.commit()

    urgent = [k for k, v in body.red_flags.items() if v and defs[k].route == "urgent_care"]
    return {"intake_id": str(row.id), "urgent": bool(urgent), "urgent_flags": urgent}


# ----- Capture sessions -------------------------------------------------------

@router.post("/sessions", status_code=201)
def open_session(body: SessionIn, user: M.User = Depends(patient), db: Session = Depends(get_db)):
    intake = db.get(M.IntakeRow, uuid.UUID(body.intake_id))
    if intake is None or intake.user_id != user.id:
        raise HTTPException(404, "intake not found")
    s = M.CaptureSession(user_id=user.id, intake_id=intake.id, app_version=body.app_version,
                         device_model=body.device_model, status="open")
    db.add(s)
    db.commit()
    return {"session_id": str(s.id), "upload_urls": _upload_urls(s.id)}


def _upload_urls(session_id: uuid.UUID) -> dict[str, str]:
    exp = now() + timedelta(seconds=settings.upload_url_seconds)
    return {v: f"/api/v1/uploads/{sign_upload(session_id, v, exp)}" for v in REQUIRED_VIEWS}


@router.post("/sessions/{session_id}/upload-urls")
def refresh_upload_urls(session_id: str, user: M.User = Depends(patient), db: Session = Depends(get_db)):
    s = own_session(db, user, session_id)
    return {"upload_urls": _upload_urls(s.id)}


@router.put("/uploads/{token}")
async def upload(token: str, request: Request, db: Session = Depends(get_db)):
    """Pre-signed upload target (dev stand-in for an S3 pre-signed PUT URL)."""
    session_id, view = verify_upload(token)
    s = db.get(M.CaptureSession, session_id)
    if s is None or s.status not in ("open", "uploaded", "needs_retake"):
        raise HTTPException(409, "session is not accepting uploads")
    data = await request.body()
    if not data or len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "image missing or larger than 15 MB")
    try:
        clean = strip_exif(data)  # server repeats the on-device EXIF strip
    except Exception:
        raise HTTPException(415, "not a readable image")
    key = f"sessions/{session_id}/{view}-{secrets.token_hex(6)}.jpg"
    storage.put(key, clean)
    return {"object_key": key, "sha256": sha256_hex(clean)}


@router.post("/sessions/{session_id}/images", status_code=201)
def register_image(session_id: str, body: ImageIn, user: M.User = Depends(patient), db: Session = Depends(get_db)):
    s = own_session(db, user, session_id)
    if not body.object_key.startswith(f"sessions/{s.id}/"):
        raise HTTPException(422, "object key does not belong to this session")
    try:
        data = storage.get(body.object_key)
    except (FileNotFoundError, ValueError):
        raise HTTPException(422, "object not uploaded")
    if sha256_hex(data) != body.sha256:
        raise HTTPException(422, "checksum mismatch")
    q = check(data, body.view)
    for old in s.images:
        if old.view == body.view and not old.superseded:
            old.superseded = True
    img = M.ImageRow(session_id=s.id, view=body.view, object_key=body.object_key, sha256=body.sha256,
                     width_px=q.width_px, height_px=q.height_px, blur_score=q.blur_score,
                     brightness_mean=q.brightness_mean, face_coverage=q.face_coverage,
                     device_checks=body.device_checks, server_checks=q.checks, quality_pass=q.quality_pass)
    s.images.append(img)
    db.flush()
    if all(v in current_images(s) for v in REQUIRED_VIEWS):
        s.status = "uploaded"
    db.commit()
    return {"image_id": str(img.id), "quality_pass": q.quality_pass, "checks": q.checks}


@router.post("/sessions/{session_id}/submit", status_code=202)
def submit(session_id: str, tasks: BackgroundTasks, user: M.User = Depends(patient), db: Session = Depends(get_db)):
    s = own_session(db, user, session_id)
    if s.status not in ("uploaded", "needs_retake", "failed"):
        if s.status == "open":
            raise HTTPException(409, "upload front, left45 and right45 first")
        raise HTTPException(409, f"session is {s.status}")
    if not all(v in current_images(s) for v in REQUIRED_VIEWS):
        raise HTTPException(409, "upload front, left45 and right45 first")
    s.status, s.error = "processing", None
    db.commit()
    # In production this is a Celery task on Redis; BackgroundTasks keeps dev dependency-free.
    tasks.add_task(process_session, s.id)
    return {"status": "processing"}


@router.get("/sessions")
def list_sessions(user: M.User = Depends(patient), db: Session = Depends(get_db)):
    rows = db.query(M.CaptureSession).filter_by(user_id=user.id).order_by(M.CaptureSession.created_at.desc()).all()
    out = []
    for s in rows:
        td = db.query(M.TriageDecision).filter_by(session_id=s.id).one_or_none()
        out.append({"session_id": str(s.id), "status": s.status, "created_at": s.created_at.isoformat(),
                    "route": td.route if td else None})
    return out


@router.get("/sessions/{session_id}/result")
def result(session_id: str, user: M.User = Depends(patient), db: Session = Depends(get_db)):
    return session_result(db, own_session(db, user, session_id))


@router.get("/sessions/{session_id}/images/{view}")
def session_image(session_id: str, view: str, user: M.User = Depends(patient), db: Session = Depends(get_db)):
    s = own_session(db, user, session_id)
    img = current_images(s).get(view)
    if img is None:
        raise HTTPException(404, "no image")
    return Response(storage.get(img.object_key), media_type="image/jpeg",
                    headers={"Cache-Control": "private, no-store"})


# ----- Summary ----------------------------------------------------------------

@router.post("/sessions/{session_id}/summary", status_code=201)
def make_summary(session_id: str, body: SummaryIn, request: Request, user: M.User = Depends(patient),
                 db: Session = Depends(get_db)):
    s = own_session(db, user, session_id)
    if s.status != "complete":
        raise HTTPException(409, "the assessment is not complete")
    if body.share_with_iconic and not latest_consents(db, user.id).get("share_with_clinic"):
        raise HTTPException(403, "turn on 'share with ICONIC' consent first")
    summary_id = uuid.uuid4()
    token = secrets.token_urlsafe(24) if body.share_with_iconic else None
    share_url = f"{str(request.base_url).rstrip('/')}/clinic/s/{token}" if token else None
    data = build_data(db, s, str(summary_id))
    keys = {v: i.object_key for v, i in current_images(s).items() if v in REQUIRED_VIEWS}
    pdf = render_pdf(data, keys, share_url)
    pdf_key = f"summaries/{s.user_id}/{summary_id}.pdf"
    storage.put(pdf_key, pdf)
    row = M.ConsultationSummary(id=summary_id, session_id=s.id, pdf_object_key=pdf_key, data=data,
                                share_token_hash=sha256_hex(token) if token else None,
                                shared_with="iconic_clinic" if token else "patient_only",
                                expires_at=now() + timedelta(days=settings.share_link_days) if token else None)
    db.add(row)
    audit(db, user, "export_pdf", "consultation_summary", summary_id, request,
          {"shared_with": row.shared_with})
    db.commit()
    return {"summary_id": str(summary_id), "pdf_url": f"/api/v1/summaries/{summary_id}/pdf",
            "shared_with": row.shared_with, "share_url": share_url,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None, "data": data}


@router.get("/summaries/{summary_id}/pdf")
def summary_pdf(summary_id: str, request: Request, user: M.User = Depends(patient), db: Session = Depends(get_db)):
    row = db.get(M.ConsultationSummary, uuid.UUID(summary_id))
    if row is None or db.get(M.CaptureSession, row.session_id).user_id != user.id:
        raise HTTPException(404, "summary not found")
    audit(db, user, "download_pdf", "consultation_summary", summary_id, request)
    db.commit()
    return Response(storage.get(row.pdf_object_key), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="dermalens-summary-{summary_id[:8]}.pdf"'})


# ----- Data subject rights ----------------------------------------------------

@router.get("/me/export")
def export_me(request: Request, user: M.User = Depends(patient), db: Session = Depends(get_db)):
    sessions = db.query(M.CaptureSession).filter_by(user_id=user.id).all()
    audit(db, user, "export_data", "user", user.id, request)
    db.commit()
    return {
        "email": user.email, "created_at": user.created_at.isoformat(), "profile": get_profile(user, db),
        "consents": latest_consents(db, user.id),
        "allergens": [{"ingredient_id": a.ingredient_id, "family_code": a.family_code, "raw_text": a.raw_text}
                      for a in db.query(M.UserAllergen).filter_by(user_id=user.id)],
        "sessions": [session_result(db, s) for s in sessions],
        "images": [{"session_id": str(s.id), "view": i.view, "url": f"/api/v1/sessions/{s.id}/images/{i.view}"}
                   for s in sessions for i in current_images(s).values()],
    }


@router.delete("/me", status_code=202)
def delete_me(request: Request, user: M.User = Depends(patient), db: Session = Depends(get_db)):
    """Erasure request: images and personal data are purged now; the account is closed."""
    for s in db.query(M.CaptureSession).filter_by(user_id=user.id):
        storage.delete_prefix(f"sessions/{s.id}")
    storage.delete_prefix(f"summaries/{user.id}")
    p = db.get(M.PatientProfile, user.id)
    if p is not None:
        p.full_name_enc = encrypt("[erased]")
        p.birth_year = None
    for i in db.query(M.IntakeRow).filter_by(user_id=user.id):
        i.free_text_enc = None
    db.query(M.UserAllergen).filter_by(user_id=user.id).delete()
    db.query(M.RefreshToken).filter_by(user_id=user.id).delete()
    user.email = f"erased-{user.id}@invalid"
    user.deleted_at = now()
    audit(db, user, "delete_account", "user", user.id, request)
    db.commit()
    return {"status": "erased"}
