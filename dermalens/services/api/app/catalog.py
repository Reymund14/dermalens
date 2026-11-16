"""Load database rows into the rules package's immutable types."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from dermalens_rules import (
    ConflictRule, Contraindication, Inference, Ingredient, Intake, LabelResult, Product, RedFlag, ReportedConcern,
    RuleSet,
)

from . import models as M


def rule_set_version(db: Session) -> str:
    row = db.get(M.AppSetting, "rule_set_version")
    return row.value if row else "rules-unknown"


def load_rules(db: Session) -> RuleSet:
    return RuleSet(
        version=rule_set_version(db),
        conflicts=tuple(ConflictRule(r.family_a, r.family_b, r.scope, r.resolution, r.rationale)
                        for r in db.query(M.IngredientConflict).order_by(M.IngredientConflict.family_a,
                                                                         M.IngredientConflict.family_b)),
        contraindications=tuple(Contraindication(r.condition_code, r.family_code, r.ingredient_id, r.action)
                                for r in db.query(M.ContraindicationRow).order_by(M.ContraindicationRow.condition_code)),
    )


def load_ingredients(db: Session) -> dict[str, Ingredient]:
    fams: dict[str, set[str]] = defaultdict(set)
    for m in db.query(M.IngredientFamilyMember):
        fams[m.ingredient_id].add(m.family_code)
    bens: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for b in db.query(M.IngredientConcernBenefit).order_by(M.IngredientConcernBenefit.concern_code):
        bens[b.ingredient_id].append((b.concern_code, float(b.weight)))
    return {
        i.id: Ingredient(id=i.id, inci_name=i.inci_name, families=frozenset(fams[i.id]),
                         irritancy_level=i.irritancy_level, is_active=i.is_active,
                         photosensitizing=i.photosensitizing, pregnancy_avoid=i.pregnancy_avoid,
                         benefits=tuple(bens[i.id]))
        for i in db.query(M.Ingredient)
    }


def to_product(p: M.Product, ings: dict[str, Ingredient]) -> Product:
    return Product(
        id=p.id, brand=p.brand, name=p.name, category=p.category,
        suitable_skin_types=frozenset(p.suitable_skin_types),
        ingredients=tuple(ings[pi.ingredient_id] for pi in p.ingredients),
        spf=p.spf, pa_rating=p.pa_rating, price_php=float(p.price_php or 0),
        stocked_by_iconic=p.stocked_by_iconic, is_listed=p.is_listed,
        fda_notification_no=p.fda.notification_no if p.fda else None,
    )


def load_catalog(db: Session) -> tuple[Product, ...]:
    ings = load_ingredients(db)
    return tuple(to_product(p, ings) for p in db.query(M.Product).order_by(M.Product.id))


def build_intake(db: Session, intake: M.IntakeRow, profile: M.PatientProfile | None) -> Intake:
    flag_routes = {f.code: f.route for f in db.query(M.RedFlagDefinition)}
    allergens = db.query(M.UserAllergen).filter_by(user_id=intake.user_id).all()
    return Intake(
        concerns=tuple(ReportedConcern(c.concern_code, c.self_severity or 1, c.duration_weeks or 0)
                       for c in sorted(intake.concerns, key=lambda c: c.concern_code)),
        red_flags_true=tuple(RedFlag(f.red_flag_code, flag_routes[f.red_flag_code])
                             for f in intake.red_flags if f.answer),
        skin_type=(profile.skin_type if profile and profile.skin_type else "normal"),
        pregnant_or_breastfeeding=bool(profile and profile.is_pregnant_or_breastfeeding),
        on_isotretinoin=intake.on_isotretinoin,
        current_rx_topicals=intake.current_rx_topicals,
        allergen_ingredient_ids=frozenset(a.ingredient_id for a in allergens if a.ingredient_id),
        allergen_families=frozenset(a.family_code for a in allergens if a.family_code),
        reacted_product_ids=frozenset(r.product_id for r in intake.routine_items
                                      if r.product_id and r.reaction_reported),
        current_product_ids=frozenset(r.product_id for r in intake.routine_items if r.product_id),
        uses_actives_without_reaction=intake.uses_actives_without_reaction,
    )


def to_inference(raw: dict) -> Inference:
    return Inference(
        model_version_id=raw["model_version_id"], quality_pass=raw["quality_pass"], ood_score=raw["ood_score"],
        ood_flag=raw["ood_flag"], refer_out_probability=raw["refer_out_probability"],
        labels={k: LabelResult(p=v["p"], present=v["present"], grade=v["grade"], uncertain=v["uncertain"])
                for k, v in raw["labels"].items()},
        thresholds=raw.get("thresholds", {"refer_out": 0.30}),
    )
