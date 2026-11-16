"""Catalog, rule and model maintenance. Every write is audited; rule edits bump
the rule-set version."""
from __future__ import annotations

import re
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models as M
from .. import storage
from ..config import settings
from ..db import get_db
from ..present import product_card
from ..schemas import ConflictIn, FdaVerifyIn, ProductIn, StaffUserIn, UserPatchIn
from ..security import audit, hash_password, now, require

router = APIRouter(prefix="/admin", tags=["admin"])
admin = require("admin")

# Actives regulated as drugs in the Philippines; never allowed in the cosmetic catalog.
DRUG_ONLY_INCI = {"tretinoin", "adapalene", "hydroquinone", "clindamycin", "clindamycin phosphate", "isotretinoin",
                  "tazarotene", "erythromycin", "metronidazole"}


def _bump_rule_version(db: Session) -> str:
    row = db.get(M.AppSetting, "rule_set_version")
    major, minor, patch = (int(x) for x in re.findall(r"\d+", row.value)[:3])
    row.value = f"rules-{major}.{minor + 1}.0"
    return row.value


@router.get("/products")
def list_products(user: M.User = Depends(admin), db: Session = Depends(get_db)):
    out = []
    for p in db.query(M.Product).order_by(M.Product.id):
        card = product_card(p)
        card.update(is_listed=p.is_listed, verified_on=p.fda.verified_on.isoformat() if p.fda else None)
        out.append(card)
    return out


@router.post("/products", status_code=201)
def create_product(body: ProductIn, request: Request, user: M.User = Depends(admin), db: Session = Depends(get_db)):
    if db.get(M.Product, body.id):
        raise HTTPException(409, "product id exists")
    terms = [t.strip().lower() for t in body.inci]
    drugs = sorted(set(terms) & DRUG_ONLY_INCI)
    if drugs:
        raise HTTPException(422, {"drug_ingredients": drugs, "detail": "drug-regulated actives cannot be listed"})
    ids, unmapped = [], []
    for t in terms:
        syn = db.get(M.IngredientSynonym, t)
        (ids.append(syn.ingredient_id) if syn else unmapped.append(t))
    if unmapped:
        raise HTTPException(422, {"unmapped_inci": unmapped,
                                  "detail": "map every INCI term through the synonym table before listing"})
    p = M.Product(id=body.id, brand=body.brand, name=body.name, category=body.category,
                  suitable_skin_types=sorted(body.suitable_skin_types), spf=body.spf, pa_rating=body.pa_rating,
                  price_php=body.price_php, stocked_by_iconic=body.stocked_by_iconic, is_listed=False)
    seen = []
    for i in ids:
        if i not in seen:
            seen.append(i)
    p.ingredients = [M.ProductIngredient(ingredient_id=i, position=n) for n, i in enumerate(seen, start=1)]
    db.add(p)
    audit(db, user, "create_product", "product", p.id, request)
    db.commit()
    return {**product_card(p), "is_listed": False,
            "next_step": "record the FDA verification to list this product"}


@router.post("/products/{product_id}/verify")
def verify_product(product_id: str, body: FdaVerifyIn, request: Request, user: M.User = Depends(admin),
                   db: Session = Depends(get_db)):
    p = db.get(M.Product, product_id)
    if p is None:
        raise HTTPException(404, "product not found")
    row = db.get(M.ProductFdaNotification, product_id) or M.ProductFdaNotification(product_id=product_id)
    row.notification_no, row.evidence_uri = body.notification_no, body.evidence_uri
    row.verified_on, row.verified_by = date.today(), user.id
    row.valid_until = date.fromisoformat(body.valid_until) if body.valid_until else None
    db.merge(row)
    p.is_listed = True
    audit(db, user, "verify_product", "product", product_id, request, {"notification_no": body.notification_no})
    db.commit()
    return {"product_id": product_id, "is_listed": True}


@router.post("/products/{product_id}/delist")
def delist_product(product_id: str, request: Request, user: M.User = Depends(admin), db: Session = Depends(get_db)):
    p = db.get(M.Product, product_id)
    if p is None:
        raise HTTPException(404, "product not found")
    p.is_listed = False
    audit(db, user, "delist_product", "product", product_id, request)
    db.commit()
    return {"product_id": product_id, "is_listed": False}


@router.get("/rules")
def get_rules(user: M.User = Depends(admin), db: Session = Depends(get_db)):
    return {
        "rule_set_version": db.get(M.AppSetting, "rule_set_version").value,
        "conflicts": [{"id": str(c.id), "family_a": c.family_a, "family_b": c.family_b, "scope": c.scope,
                       "resolution": c.resolution, "rationale": c.rationale} for c in db.query(M.IngredientConflict)],
        "contraindications": [{"condition": c.condition_code, "family": c.family_code, "ingredient": c.ingredient_id,
                               "action": c.action} for c in db.query(M.ContraindicationRow)],
    }


@router.post("/rules/conflicts", status_code=201)
def add_conflict(body: ConflictIn, request: Request, user: M.User = Depends(admin), db: Session = Depends(get_db)):
    for f in (body.family_a, body.family_b):
        if not db.get(M.IngredientFamily, f):
            raise HTTPException(422, f"unknown family {f}")
    version = _bump_rule_version(db)
    db.add(M.IngredientConflict(**body.model_dump(), rule_set_version=version))
    audit(db, user, "update_rule", "ingredient_conflict", f"{body.family_a}+{body.family_b}", request,
          {"new_version": version})
    db.commit()
    return {"rule_set_version": version}


@router.post("/models/{model_id}/activate")
def activate_model(model_id: str, request: Request, user: M.User = Depends(admin), db: Session = Depends(get_db)):
    mv = db.get(M.ModelVersion, model_id)
    if mv is None:
        raise HTTPException(404, "model version not registered")
    if not mv.eval_report_uri or mv.eval_report_uri.startswith("none"):
        raise HTTPException(409, "attach an evaluation report before activating")
    db.query(M.ModelVersion).update({"is_active": False})
    mv.is_active, mv.released_at = True, now()
    audit(db, user, "activate_model", "model_version", model_id, request)
    db.commit()
    return {"active": model_id}


@router.post("/jobs/delist-stale")
def delist_stale(request: Request, user: M.User = Depends(admin), db: Session = Depends(get_db)):
    """Nightly job: delist products whose FDA check is older than 90 days."""
    return {"delisted": run_delist_stale(db, user, request)}


def run_delist_stale(db: Session, actor: M.User | None = None, request: Request | None = None) -> list[str]:
    cutoff = date.today() - timedelta(days=settings.fda_reverify_days)
    out = []
    for p in db.query(M.Product).filter_by(is_listed=True):
        if p.fda is None or p.fda.verified_on < cutoff or (p.fda.valid_until and p.fda.valid_until < date.today()):
            p.is_listed = False
            out.append(p.id)
            audit(db, actor, "auto_delist", "product", p.id, request)
    db.commit()
    return out


@router.post("/jobs/purge-images")
def purge_images(request: Request, user: M.User = Depends(admin), db: Session = Depends(get_db)):
    """Retention job: images 12 months after last activity, or 24 h when storage consent is off."""
    from .patient import latest_consents

    purged = 0
    for s in db.query(M.CaptureSession):
        age = now() - (s.created_at if s.created_at.tzinfo else s.created_at.replace(tzinfo=now().tzinfo))
        keep = latest_consents(db, s.user_id).get("image_storage", False)
        limit = timedelta(days=30 * settings.retention_months) if keep else timedelta(hours=24)
        if age > limit and s.images:
            storage.delete_prefix(f"sessions/{s.id}")
            for i in s.images:
                i.object_key = "purged"
            purged += 1
    audit(db, user, "purge_images", "capture_session", "*", request, {"sessions": purged})
    db.commit()
    return {"sessions_purged": purged}


# ----- Dashboard, accounts, models, audit -------------------------------------

@router.get("/dashboard")
def dashboard(user: M.User = Depends(admin), db: Session = Depends(get_db)):
    from dermalens_rules.triage import RULE_SET_VERSION as TRIAGE_VERSION

    roles = {r: db.query(M.User).filter_by(role=r, deleted_at=None).count()
             for r in ("patient", "clinic_staff", "dermatologist", "admin")}
    routes = {}
    for td in db.query(M.TriageDecision):
        routes[td.route] = routes.get(td.route, 0) + 1
    shared = db.query(M.ConsultationSummary).filter_by(shared_with="iconic_clinic")
    version = db.get(M.AppSetting, "rule_set_version").value
    active = db.query(M.ModelVersion).filter_by(is_active=True).first()
    return {
        "users": roles,
        "disabled_users": db.query(M.User).filter(M.User.disabled_at.isnot(None)).count(),
        "sessions": db.query(M.CaptureSession).count(),
        "sessions_by_status": {s: db.query(M.CaptureSession).filter_by(status=s).count()
                               for s in ("open", "uploaded", "processing", "needs_retake", "complete", "failed")},
        "routes": routes,
        "shared_summaries": shared.count(),
        "unreviewed_summaries": shared.filter(M.ConsultationSummary.reviewed_at.is_(None)).count(),
        "products_listed": db.query(M.Product).filter_by(is_listed=True).count(),
        "products_unlisted": db.query(M.Product).filter_by(is_listed=False).count(),
        "rule_set_version": version, "triage_version": TRIAGE_VERSION,
        "rules_signed_off": db.query(M.RuleSignoff).filter_by(rule_set_version=version,
                                                              triage_version=TRIAGE_VERSION).count() > 0,
        "active_model": active.id if active else None,
        "derm_reviews": db.query(M.DermReview).count(),
    }


def _user_out(u: M.User) -> dict:
    return {"id": str(u.id), "email": u.email, "role": u.role, "display_name": u.display_name,
            "disabled": u.disabled_at is not None, "created_at": u.created_at.isoformat()}


@router.get("/users")
def list_users(role: str | None = None, user: M.User = Depends(admin), db: Session = Depends(get_db)):
    """Staff, dermatologist and admin accounts. Patients are counted on the
    dashboard but not listed: admins have no need to browse patient accounts."""
    q = db.query(M.User).filter(M.User.deleted_at.is_(None), M.User.role != "patient")
    if role:
        q = q.filter_by(role=role)
    return [_user_out(u) for u in q.order_by(M.User.role, M.User.email)]


@router.post("/users", status_code=201)
def create_user(body: StaffUserIn, request: Request, user: M.User = Depends(admin), db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.query(M.User).filter_by(email=email).first():
        raise HTTPException(409, "an account with this email already exists")
    u = M.User(email=email, role=body.role, display_name=body.display_name,
               password_hash=hash_password(body.password), created_by=user.id)
    db.add(u)
    db.flush()
    audit(db, user, "create_user", "user", u.id, request, {"role": body.role})
    db.commit()
    return _user_out(u)


@router.patch("/users/{user_id}")
def update_user(user_id: str, body: UserPatchIn, request: Request, user: M.User = Depends(admin),
                db: Session = Depends(get_db)):
    u = db.get(M.User, uuid.UUID(user_id))
    if u is None or u.deleted_at is not None or u.role == "patient":
        raise HTTPException(404, "account not found")
    if u.id == user.id and (body.disabled or (body.role and body.role != "admin")):
        raise HTTPException(409, "you cannot disable or demote your own account")
    changes = {}
    if body.role is not None and body.role != u.role:
        changes["role"] = [u.role, body.role]
        u.role = body.role
    if body.display_name is not None:
        u.display_name = body.display_name
        changes["display_name"] = True
    if body.disabled is not None and body.disabled != (u.disabled_at is not None):
        u.disabled_at = now() if body.disabled else None
        changes["disabled"] = body.disabled
    if body.password is not None:
        u.password_hash = hash_password(body.password)
        changes["password_reset"] = True
    if changes.get("disabled") or "password_reset" in changes or "role" in changes:
        # Sign the account out everywhere; access tokens lapse within 15 minutes and
        # current_user re-checks disabled status on every request.
        db.query(M.RefreshToken).filter_by(user_id=u.id, revoked_at=None).update({"revoked_at": now()})
    audit(db, user, "update_user", "user", u.id, request, changes)
    db.commit()
    return _user_out(u)


@router.get("/models")
def list_models(user: M.User = Depends(admin), db: Session = Depends(get_db)):
    return [{"id": m.id, "architecture": m.architecture, "artifact_sha256": m.artifact_sha256,
             "eval_report_uri": m.eval_report_uri, "is_active": m.is_active,
             "released_at": m.released_at.isoformat() if m.released_at else None,
             "can_activate": bool(m.eval_report_uri) and not m.eval_report_uri.startswith("none")}
            for m in db.query(M.ModelVersion).order_by(M.ModelVersion.id)]


@router.get("/audit")
def audit_log(action: str | None = None, entity: str | None = None, limit: int = 100,
              user: M.User = Depends(admin), db: Session = Depends(get_db)):
    q = db.query(M.AuditLog)
    if action:
        q = q.filter_by(action=action)
    if entity:
        q = q.filter_by(entity=entity)
    rows = q.order_by(M.AuditLog.id.desc()).limit(min(max(limit, 1), 500)).all()
    actors = {u.id: u for u in db.query(M.User).filter(M.User.id.in_({r.actor_id for r in rows if r.actor_id}))}

    def who(r):
        a = actors.get(r.actor_id)
        if a is None:
            return {"name": "system", "role": None}
        # Patients are shown by role only, never by email.
        return {"name": "patient" if a.role == "patient" else (a.display_name or a.email), "role": a.role}

    return [{"id": r.id, "at": r.at.isoformat(), "actor": who(r), "action": r.action, "entity": r.entity,
             "entity_id": r.entity_id, "detail": r.detail} for r in rows]
