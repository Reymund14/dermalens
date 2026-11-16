"""Create tables and load reference data, rules and the SAMPLE catalog.

    python -m app.seed            # idempotent; safe to re-run

Dev accounts are created only when SEED_DEV_ACCOUNTS=1 (the default for local
runs). Never enable that in production.
"""
from __future__ import annotations

import os
from datetime import date

from sqlalchemy.orm import Session

from dermalens_inference.classifier import STUB_CONFIG
from dermalens_rules import seed as S
from dermalens_rules.triage import RULE_SET_VERSION as TRIAGE_VERSION

from . import models as M
from .db import Base, SessionLocal, engine
from .security import hash_password

DEV_ACCOUNTS = [
    ("admin.dev@example.com", "admin", "AdminPass!2026", "Dev Admin"),
    ("staff.dev@example.com", "clinic_staff", "StaffPass!2026", "Dev Front Desk"),
    ("derm.dev@example.com", "dermatologist", "DermPass!2026", "Dr. Dev Dermatologist"),
]


def _upsert(db: Session, obj):
    db.merge(obj)


def seed(db: Session, dev_accounts: bool = True) -> None:
    admin = db.query(M.User).filter_by(role="admin").first()
    if dev_accounts:
        for email, role, pw, name in DEV_ACCOUNTS:
            if not db.query(M.User).filter_by(email=email).first():
                db.add(M.User(email=email, role=role, password_hash=hash_password(pw), display_name=name))
        db.flush()
        admin = db.query(M.User).filter_by(email="admin.dev@example.com").one()
    if admin is None:
        raise SystemExit("create an admin user first (SEED_DEV_ACCOUNTS=0 and no admin exists)")

    for code, name, is_label in S.CONCERNS:
        _upsert(db, M.Concern(code=code, display_name=name, model_label=is_label))
    for code, q, route in S.RED_FLAGS:
        _upsert(db, M.RedFlagDefinition(code=code, question_text=q, route=route, rule_set_version=TRIAGE_VERSION))
    for code, name in S.FAMILIES:
        _upsert(db, M.IngredientFamily(code=code, display_name=name))
    db.flush()
    for ing in S.INGREDIENTS.values():
        _upsert(db, M.Ingredient(id=ing.id, inci_name=ing.inci_name, irritancy_level=ing.irritancy_level,
                                 is_active=ing.is_active, photosensitizing=ing.photosensitizing,
                                 pregnancy_avoid=ing.pregnancy_avoid))
    db.flush()
    for ing in S.INGREDIENTS.values():
        for fam in ing.families:
            _upsert(db, M.IngredientFamilyMember(family_code=fam, ingredient_id=ing.id))
        for concern, w in ing.benefits:
            _upsert(db, M.IngredientConcernBenefit(ingredient_id=ing.id, concern_code=concern, weight=w,
                                                   evidence_note="Seed value; confirm with cosmetic chemist review"))
    synonyms = {ing.inci_name.lower(): ing.id for ing in S.INGREDIENTS.values()}
    synonyms.update({syn.lower(): ing_id for syn, ing_id in S.SYNONYMS.items()})
    for syn, ing_id in sorted(synonyms.items()):
        _upsert(db, M.IngredientSynonym(synonym=syn, ingredient_id=ing_id))

    if not db.query(M.IngredientConflict).first():
        for r in S.CONFLICTS:
            db.add(M.IngredientConflict(family_a=r.family_a, family_b=r.family_b, scope=r.scope,
                                        resolution=r.resolution, rationale=r.rationale,
                                        rule_set_version=S.RULE_SET_VERSION))
        for c in S.CONTRAINDICATIONS:
            db.add(M.ContraindicationRow(condition_code=c.condition_code, family_code=c.family_code,
                                         ingredient_id=c.ingredient_id, action=c.action,
                                         rule_set_version=S.RULE_SET_VERSION))
    _upsert(db, M.AppSetting(key="rule_set_version", value=S.RULE_SET_VERSION))
    db.flush()

    for p in S.sample_products():
        if db.get(M.Product, p.id):
            continue
        row = M.Product(id=p.id, brand=p.brand, name=p.name, category=p.category,
                        suitable_skin_types=sorted(p.suitable_skin_types), spf=p.spf, pa_rating=p.pa_rating,
                        price_php=p.price_php, stocked_by_iconic=p.stocked_by_iconic, is_listed=p.is_listed)
        row.ingredients = [M.ProductIngredient(ingredient_id=i.id, position=n)
                           for n, i in enumerate(p.ingredients, start=1)]
        db.add(row)
        db.flush()
        if p.fda_notification_no:
            db.add(M.ProductFdaNotification(product_id=p.id, notification_no=p.fda_notification_no,
                                            verified_on=date.today(), verified_by=admin.id,
                                            evidence_uri="sample://not-a-real-verification"))

    if not db.get(M.ModelVersion, STUB_CONFIG.model_version_id):
        db.add(M.ModelVersion(id=STUB_CONFIG.model_version_id, architecture=STUB_CONFIG.architecture,
                              artifact_sha256="0" * 64, thresholds=STUB_CONFIG.thresholds,
                              temperature=STUB_CONFIG.temperature,
                              eval_report_uri="none: development stub, not evaluated", is_active=True))
    db.commit()


def main() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db, dev_accounts=os.getenv("SEED_DEV_ACCOUNTS", "1") == "1")
    print("Seeded. Dev accounts:" if os.getenv("SEED_DEV_ACCOUNTS", "1") == "1" else "Seeded.")
    if os.getenv("SEED_DEV_ACCOUNTS", "1") == "1":
        for email, role, pw, _ in DEV_ACCOUNTS:
            print(f"  {role:13s} {email}  /  {pw}")


if __name__ == "__main__":
    main()
