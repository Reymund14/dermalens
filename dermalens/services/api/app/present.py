"""Build user-facing result payloads from stored rows, using only the
reviewed copy table (vocabulary lock)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from dermalens_rules import copy as C

from . import models as M
from .pipeline import current_images


def band(p: float) -> str:
    return "low" if p < 0.4 else "medium" if p < 0.7 else "high"


def product_card(p: M.Product) -> dict:
    return {
        "id": p.id, "brand": p.brand, "name": p.name, "category": p.category, "spf": p.spf,
        "pa_rating": p.pa_rating, "price_php": float(p.price_php) if p.price_php is not None else None,
        "stocked_by_iconic": p.stocked_by_iconic,
        "fda_notification_no": p.fda.notification_no if p.fda else None,
        "ingredients": [pi.ingredient_id for pi in p.ingredients],
    }


def session_result(db: Session, s: M.CaptureSession) -> dict:
    out: dict = {"session_id": str(s.id), "status": s.status, "created_at": s.created_at.isoformat(),
                 "boundary": C.BOUNDARY_STATEMENT}
    imgs = current_images(s)
    out["images"] = {v: {"quality_pass": i.quality_pass, "server_checks": i.server_checks}
                     for v, i in imgs.items()}
    if s.status == "needs_retake":
        out["retake_views"] = sorted(v for v, i in imgs.items() if not i.quality_pass) or ["front", "left45",
                                                                                            "right45"]
        out["message"] = "Some photos could not be checked. Please retake them following the guide."
        return out
    if s.status == "failed":
        out["message"] = "Something went wrong while checking your photos. Please try again."
        return out
    if s.status != "complete":
        return out

    td = db.query(M.TriageDecision).filter_by(session_id=s.id).one()
    inf = db.get(M.InferenceRow, td.inference_id) if td.inference_id else None
    questions = {f.code: f.question_text for f in db.query(M.RedFlagDefinition)}
    out["route"] = {"code": td.route, **C.ROUTES[td.route]}
    out["reasons"] = [{"code": r, "text": C.reason_text(r, questions)} for r in td.reasons]
    out["findings"] = []
    if inf is not None and inf.quality_pass and td.route != "urgent_care":
        for lab in sorted(inf.labels, key=lambda l: l.concern_code):
            out["findings"].append({
                "code": lab.concern_code, "name": C.CONCERN_NAMES[lab.concern_code], "present": lab.present,
                "grade": lab.grade, "grade_name": C.GRADE_NAMES[lab.grade], "band": band(lab.probability),
                "uncertain": lab.uncertain,
            })
    rec = db.query(M.Recommendation).filter_by(triage_id=td.id).one_or_none()
    if rec is None:
        out["routine"] = None
    else:
        def items(tod):
            return [{"step": i.step_order, "slot": i.slot, "frequency": i.frequency, "why": i.why,
                     "patch_test": i.patch_test, "product": product_card(i.product)}
                    for i in rec.items if i.time_of_day == tod]
        out["routine"] = {"status": rec.status, "am": items("am"), "pm": items("pm"), "notes": rec.notes,
                          "basics_only": td.route == "dermatologist"}
    out["versions"] = {
        "model": inf.model_version_id if inf else None,
        "triage_rules": td.rule_set_version,
        "recommendation_rules": rec.rule_set_version if rec else None,
        "catalog_snapshot_at": rec.catalog_snapshot_at.isoformat() if rec else None,
        "input_hash": rec.input_hash if rec else None,
        "copy": C.COPY_VERSION,
    }
    return out
