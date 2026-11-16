"""Dermatologist endpoints: independent case review, rule sign-off and the
agreement figures used for Level 3 (clinical agreement) evaluation."""
from __future__ import annotations

import uuid
from collections import Counter

from dermalens_rules.triage import RULE_SET_VERSION as TRIAGE_VERSION
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models as M
from ..db import get_db
from ..schemas import DermReviewIn, SignoffIn
from ..security import audit, require
from .clinic import _brief, _live

router = APIRouter(prefix="/derm", tags=["dermatologist"])
derm = require("dermatologist")

# Routes ordered from most to least urgent; a "missed referral" is any case the
# dermatologist put on a more urgent route than the app did.
URGENCY = {"urgent_care": 0, "dermatologist": 1, "iconic_clinic": 2, "self_care": 3}
REFER = {"urgent_care", "dermatologist"}


def _app_route(r: M.ConsultationSummary) -> str:
    return (r.data.get("route") or {}).get("code") or "self_care"


def _review_out(v: M.DermReview) -> dict:
    return {"id": str(v.id), "summary_id": str(v.summary_id), "app_route": v.app_route, "derm_route": v.derm_route,
            "concern_agreement": v.concern_agreement, "note": v.note, "created_at": v.created_at.isoformat()}


@router.get("/queue")
def queue(include_reviewed: bool = False, user: M.User = Depends(derm), db: Session = Depends(get_db)):
    """Shared cases, those the app routed to a dermatologist first, then newest."""
    mine = {v.summary_id: v for v in db.query(M.DermReview).filter_by(reviewer_id=user.id)}
    rows = db.query(M.ConsultationSummary).filter_by(shared_with="iconic_clinic").order_by(
        M.ConsultationSummary.created_at.desc()).limit(300).all()
    out = []
    for r in rows:
        if r.id in mine and not include_reviewed:
            continue
        out.append({**_brief(r), "my_review": _review_out(mine[r.id]) if r.id in mine else None})
    out.sort(key=lambda b: URGENCY.get(b["route"] or "self_care", 3))
    return out


@router.post("/summaries/{summary_id}/review", status_code=201)
def review(summary_id: str, body: DermReviewIn, request: Request, user: M.User = Depends(derm),
           db: Session = Depends(get_db)):
    row = _live(db.get(M.ConsultationSummary, uuid.UUID(summary_id)))
    codes = {f["code"] for f in row.data.get("visual_prescreen") or []}
    unknown = sorted(set(body.concern_agreement) - codes)
    if unknown:
        raise HTTPException(422, {"unknown_concerns": unknown})
    v = db.query(M.DermReview).filter_by(summary_id=row.id, reviewer_id=user.id).one_or_none()
    if v is None:
        v = M.DermReview(summary_id=row.id, reviewer_id=user.id, app_route=_app_route(row))
        db.add(v)
    v.derm_route, v.concern_agreement, v.note = body.derm_route, body.concern_agreement, body.note
    audit(db, user, "derm_review", "consultation_summary", row.id, request,
          {"app_route": v.app_route, "derm_route": v.derm_route})
    db.commit()
    return _review_out(v)


@router.get("/rules")
def rules(user: M.User = Depends(derm), db: Session = Depends(get_db)):
    """Read-only view of what the app's triage and routines are built on."""
    version = db.get(M.AppSetting, "rule_set_version").value
    signoffs = db.query(M.RuleSignoff).order_by(M.RuleSignoff.signed_at.desc()).all()
    names = {u.id: u.display_name or u.email for u in db.query(M.User).filter(
        M.User.id.in_([s.signed_by for s in signoffs]))} if signoffs else {}
    current = [s for s in signoffs if s.rule_set_version == version and s.triage_version == TRIAGE_VERSION]
    return {
        "triage_version": TRIAGE_VERSION, "rule_set_version": version,
        "signed_off": bool(current),
        "red_flags": [{"code": f.code, "question": f.question_text, "route": f.route}
                      for f in db.query(M.RedFlagDefinition).order_by(M.RedFlagDefinition.code)],
        "conflicts": [{"family_a": c.family_a, "family_b": c.family_b, "scope": c.scope, "resolution": c.resolution,
                       "rationale": c.rationale} for c in db.query(M.IngredientConflict)],
        "contraindications": [{"condition": c.condition_code, "family": c.family_code, "ingredient": c.ingredient_id,
                               "action": c.action} for c in db.query(M.ContraindicationRow)],
        "signoffs": [{"triage_version": s.triage_version, "rule_set_version": s.rule_set_version,
                      "signed_by": names.get(s.signed_by), "note": s.note, "signed_at": s.signed_at.isoformat()}
                     for s in signoffs],
    }


@router.post("/rules/signoff", status_code=201)
def signoff(body: SignoffIn, request: Request, user: M.User = Depends(derm), db: Session = Depends(get_db)):
    version = db.get(M.AppSetting, "rule_set_version").value
    s = M.RuleSignoff(triage_version=TRIAGE_VERSION, rule_set_version=version, signed_by=user.id, note=body.note)
    db.add(s)
    audit(db, user, "rule_signoff", "rule_set", version, request, {"triage_version": TRIAGE_VERSION})
    db.commit()
    return {"triage_version": TRIAGE_VERSION, "rule_set_version": version, "signed_at": s.signed_at.isoformat()}


@router.get("/stats")
def stats(user: M.User = Depends(derm), db: Session = Depends(get_db)):
    """Agreement between the app and dermatologist reviews (all reviewers)."""
    reviews = db.query(M.DermReview).all()
    n = len(reviews)
    agree = sum(v.app_route == v.derm_route for v in reviews)
    missed = [v for v in reviews if URGENCY[v.derm_route] < URGENCY.get(v.app_route, 3)]
    over = [v for v in reviews if URGENCY[v.derm_route] > URGENCY.get(v.app_route, 3)]
    should_refer = [v for v in reviews if v.derm_route in REFER]
    caught = [v for v in should_refer if v.app_route in REFER]
    yes, total = Counter(), Counter()
    for v in reviews:
        for code, ok in (v.concern_agreement or {}).items():
            total[code] += 1
            yes[code] += bool(ok)
    return {
        "reviews": n,
        "route_agreement": agree / n if n else None,
        "missed_referrals": len(missed),
        "missed_referral_cases": [str(v.summary_id) for v in missed],
        "over_referrals": len(over),
        "referral_sensitivity": len(caught) / len(should_refer) if should_refer else None,
        "concern_agreement": {c: {"agree": yes[c], "of": total[c], "rate": yes[c] / total[c]} for c in sorted(total)},
        "confusion": [{"app_route": a, "derm_route": d, "n": k} for (a, d), k in
                      sorted(Counter((v.app_route, v.derm_route) for v in reviews).items())],
    }
