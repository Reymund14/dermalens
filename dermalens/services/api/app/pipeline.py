"""Assessment pipeline: inference -> triage -> recommendation, all persisted
with the model, rule-set and catalog versions that produced them."""
from __future__ import annotations

import logging
import uuid

import httpx
from sqlalchemy.orm import Session

from dermalens_rules import Context, NoSafeProduct, UnsafeRoutine, build_routine, triage

from . import models as M
from . import storage
from .catalog import build_intake, load_catalog, load_rules, to_inference
from .config import settings
from .db import SessionLocal
from .security import now

log = logging.getLogger("dermalens.pipeline")
REQUIRED_VIEWS = ("front", "left45", "right45")


def current_images(session: M.CaptureSession) -> dict[str, M.ImageRow]:
    out: dict[str, M.ImageRow] = {}
    for img in sorted(session.images, key=lambda i: i.created_at):
        if not img.superseded:
            out[img.view] = img
    return out


def run_inference(images: dict[str, bytes]) -> dict:
    if settings.inference_url:
        files = {v: (f"{v}.jpg", data, "image/jpeg") for v, data in images.items()}
        r = httpx.post(f"{settings.inference_url.rstrip('/')}/infer", files=files, timeout=60)
        r.raise_for_status()
        return r.json()
    from dermalens_inference.service import infer  # in-process for local dev
    return infer(images)


def process_session(session_id: uuid.UUID, db: Session | None = None) -> None:
    own = db is None
    db = db or SessionLocal()
    try:
        _process(db, session_id)
    except Exception as e:  # never leave a session stuck in "processing"
        log.exception("processing failed for %s", session_id)
        db.rollback()
        s = db.get(M.CaptureSession, session_id)
        if s is not None:
            s.status, s.error = "failed", type(e).__name__
            db.commit()
    finally:
        if own:
            db.close()


def _process(db: Session, session_id: uuid.UUID) -> None:
    s = db.get(M.CaptureSession, session_id)
    imgs = current_images(s)
    raw = run_inference({v: storage.get(imgs[v].object_key) for v in REQUIRED_VIEWS})

    mv = db.get(M.ModelVersion, raw["model_version_id"])
    if mv is None:
        raise RuntimeError(f"model version {raw['model_version_id']} is not registered")

    # Keep the server's quality verdict on each image row.
    for view, q in raw.get("quality", {}).items():
        if view in imgs:
            imgs[view].server_checks = q["checks"]
            imgs[view].quality_pass = q["quality_pass"]
            imgs[view].blur_score = q["blur_score"]
            imgs[view].brightness_mean = q["brightness_mean"]
            imgs[view].face_coverage = q["face_coverage"]

    inf = M.InferenceRow(id=uuid.uuid4(), session_id=s.id, model_version_id=mv.id, quality_pass=raw["quality_pass"],
                         ood_score=raw["ood_score"], ood_flag=raw["ood_flag"],
                         refer_out_probability=raw["refer_out_probability"], raw=raw,
                         latency_ms=raw.get("latency_ms"))
    inf.labels = [M.InferenceLabel(concern_code=k, probability=v["p"], present=v["present"], grade=v["grade"],
                                   uncertain=v["uncertain"]) for k, v in raw["labels"].items()]
    db.add(inf)

    if not raw["quality_pass"] and s.quality_failures == 0:
        s.quality_failures = 1
        s.status = "needs_retake"
        db.commit()
        return
    if not raw["quality_pass"]:
        s.quality_failures += 1

    intake_row = db.get(M.IntakeRow, s.intake_id)
    profile = db.get(M.PatientProfile, s.user_id)
    intake = build_intake(db, intake_row, profile)
    inference = to_inference(raw)
    t = triage(intake, inference)
    td = M.TriageDecision(session_id=s.id, inference_id=inf.id, route=t.route, reasons=list(t.reasons),
                          rule_set_version=t.rule_set_version)
    db.add(td)
    db.flush()

    if t.route != "urgent_care":
        rules = load_rules(db)
        snapshot_at = now()
        ctx = Context(intake=intake, triage=t, inference=inference, catalog=load_catalog(db), rules=rules)
        rec = M.Recommendation(triage_id=td.id, rule_set_version=rules.version, catalog_snapshot_at=snapshot_at,
                               input_hash="", status="ok", notes=[])
        try:
            routine = build_routine(ctx)
            rec.input_hash = routine.input_hash
            rec.notes = list(routine.notes)
            rec.items = [M.RecommendationItem(time_of_day=i.time_of_day, step_order=i.step_order, slot=i.slot,
                                              product_id=i.product.id, frequency=i.frequency, why=i.why,
                                              patch_test=i.patch_test) for i in routine.items]
        except NoSafeProduct as e:
            rec.status, rec.notes = "no_safe_product", [f"No safe product for the {e.slot} step. Ask ICONIC staff."]
            rec.input_hash = "0" * 64
        except UnsafeRoutine as e:
            log.error("final safety check aborted routine for %s: %s", s.id, e)
            rec.status, rec.notes = "aborted", ["A routine could not be generated safely. Ask ICONIC staff."]
            rec.input_hash = "0" * 64
        db.add(rec)

    s.status = "complete"
    db.commit()
