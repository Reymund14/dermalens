"""Reference data the app needs before and during intake."""
from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from dermalens_rules import copy as C

from .. import models as M
from ..db import get_db
from ..present import product_card

router = APIRouter(tags=["reference"])


@router.get("/reference/boundary")
def boundary():
    return {"text": C.BOUNDARY_STATEMENT, "version": C.COPY_VERSION}


@router.get("/reference/concerns")
def concerns(db: Session = Depends(get_db)):
    return [{"code": c.code, "name": C.CONCERN_NAMES.get(c.code, c.display_name), "model_label": c.model_label}
            for c in db.query(M.Concern).order_by(M.Concern.code)]


@router.get("/reference/red-flags")
def red_flags(db: Session = Depends(get_db)):
    rows = db.query(M.RedFlagDefinition).all()
    rows.sort(key=lambda f: (f.route != "urgent_care", f.code))
    return [{"code": f.code, "question": f.question_text, "urgent": f.route == "urgent_care"} for f in rows]


@router.get("/allergens/search")
def allergen_search(q: str, db: Session = Depends(get_db)):
    """Autocomplete families and ingredients from the synonym table."""
    ql = q.strip().lower()
    if len(ql) < 2:
        return []
    fams = db.query(M.IngredientFamily).filter(
        or_(M.IngredientFamily.code.contains(ql), M.IngredientFamily.display_name.ilike(f"%{ql}%"))).limit(5).all()
    syns = db.query(M.IngredientSynonym).filter(M.IngredientSynonym.synonym.contains(ql)).limit(15).all()
    seen, out = set(), [{"kind": "family", "family_code": f.code, "label": f.display_name} for f in fams]
    for s in syns:
        if s.ingredient_id in seen:
            continue
        seen.add(s.ingredient_id)
        ing = db.get(M.Ingredient, s.ingredient_id)
        out.append({"kind": "ingredient", "ingredient_id": ing.id, "label": ing.inci_name.title(),
                    "matched": s.synonym})
    return out[:12]


@router.get("/products/search")
def product_search(q: str = "", db: Session = Depends(get_db)):
    """Search the catalog for the user's current routine (listed products only)."""
    query = db.query(M.Product).filter(M.Product.is_listed.is_(True))
    if q:
        query = query.filter(or_(M.Product.name.ilike(f"%{q}%"), M.Product.brand.ilike(f"%{q}%")))
    return [product_card(p) for p in query.order_by(M.Product.name).limit(20)]
