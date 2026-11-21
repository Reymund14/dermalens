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


ORDER = {"none": 0, "mild": 1, "moderate": 2, "marked": 3}


def compare_with_previous(db: Session, s: M.CaptureSession) -> dict | None:
    """How each concern's grade moved since the patient's previous completed check.
    Grades are the model's estimate from photos, so the wording stays cautious."""
    prev = (db.query(M.CaptureSession)
            .filter(M.CaptureSession.user_id == s.user_id, M.CaptureSession.status == "complete",
                    M.CaptureSession.created_at < s.created_at)
            .order_by(M.CaptureSession.created_at.desc()).first())
    if prev is None:
        return None

    def grades(sess: M.CaptureSession) -> tuple[dict, str | None]:
        td = db.query(M.TriageDecision).filter_by(session_id=sess.id).one_or_none()
        if td is None or td.inference_id is None or td.route == "urgent_care":
            return {}, td.route if td else None
        inf = db.get(M.InferenceRow, td.inference_id)
        if inf is None or not inf.quality_pass:
            return {}, td.route
        return {lab.concern_code: lab.grade for lab in inf.labels}, td.route

    now_g, now_route = grades(s)
    old_g, old_route = grades(prev)
    rows = []
    for code in sorted(set(now_g) | set(old_g)):
        a, b = old_g.get(code), now_g.get(code)
        trend = ("unknown" if a is None or b is None else
                 "better" if ORDER[b] < ORDER[a] else "worse" if ORDER[b] > ORDER[a] else "same")
        rows.append({"code": code, "name": C.CONCERN_NAMES[code], "trend": trend,
                     "before": C.GRADE_NAMES[a] if a is not None else None,
                     "now": C.GRADE_NAMES[b] if b is not None else None})
    days = (s.created_at - prev.created_at).days
    return {"previous_session_id": str(prev.id), "previous_at": prev.created_at.isoformat(), "days_between": days,
            "route_before": old_route, "route_now": now_route, "concerns": rows,
            "note": "Changes are estimated from photos. Lighting and angle affect them; "
                    "a dermatologist should confirm real progress."}
