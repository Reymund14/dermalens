"""Deterministic AM/PM routine builder.

A pure function of (intake, triage result, model labels, catalog snapshot,
rule set). The same inputs give the same routine byte for byte; `input_hash`
records the normalized inputs so a stored recommendation can be reproduced.
No randomness and no language model are involved.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace

from .copy import CONCERN_PHRASES
from .models import (
    GRADE_WEIGHT,
    LABELS,
    ConflictRule,
    Inference,
    Intake,
    Product,
    Routine,
    RoutineItem,
    RuleSet,
    TriageResult,
)

RECOMMENDER_VERSION = "reco-1.0.0"
BASIC_CATEGORIES = ("cleanser", "moisturizer", "sunscreen")
TREATMENT_CATEGORIES = ("serum", "treatment", "exfoliant", "toner")
PA_OK = ("PA+++", "PA++++")
MIN_SPF = 30


class NoSafeProduct(Exception):
    """A required slot has no product that passes every safety rule."""

    def __init__(self, slot: str):
        super().__init__(slot)
        self.slot = slot


class UnsafeRoutine(Exception):
    """The final safety re-check failed. The routine must not be shown."""


@dataclass(frozen=True)
class Context:
    intake: Intake
    triage: TriageResult
    inference: Inference | None
    catalog: tuple[Product, ...]
    rules: RuleSet


# ----- Hard filters -----------------------------------------------------------

def _active_conditions(intake: Intake) -> set[str]:
    conds = set()
    if intake.pregnant_or_breastfeeding:
        conds.add("pregnancy")
    if intake.on_isotretinoin:
        conds.add("isotretinoin")
    if intake.current_rx_topicals:
        conds.add("rx_topical")
    if intake.skin_type == "sensitive":
        conds.add("sensitive_skin")
    return conds


def _reaction_ingredient_ids(ctx: Context) -> frozenset[str]:
    """Ingredients to avoid because the user reacted to a product holding them.

    Water, glycerin and other inert bases would exclude the whole catalog, so
    only actives and ingredients with irritancy >= 1 are carried over.
    """
    ids: set[str] = set()
    by_id = {p.id: p for p in ctx.catalog}
    for pid in sorted(ctx.intake.reacted_product_ids):
        p = by_id.get(pid)
        if p is None:
            continue
        ids |= {i.id for i in p.ingredients if i.is_active or i.irritancy_level >= 1}
    return frozenset(ids)


def exclusion_reason(p: Product, ctx: Context) -> str | None:
    """Return why a product is excluded, or None if it may be recommended."""
    intake = ctx.intake
    if not p.is_listed or not p.fda_notification_no:
        return "not_verified"
    if p.ingredient_ids & intake.allergen_ingredient_ids:
        return "allergen_ingredient"
    if p.families & intake.allergen_families:
        return "allergen_family"
    if p.id in intake.reacted_product_ids or (p.ingredient_ids & _reaction_ingredient_ids(ctx)):
        return "reported_reaction"
    conds = _active_conditions(intake)
    for ci in ctx.rules.contraindications:
        if ci.condition_code not in conds:
            continue
        if ci.family_code is None and ci.ingredient_id is None:
            matched = True
        else:
            matched = (ci.family_code in p.families) or (ci.ingredient_id in p.ingredient_ids)
        if not matched:
            continue
        if ci.action == "exclude":
            return f"contraindication:{ci.condition_code}"
        if ci.action == "limit_wash_off" and not p.is_wash_off:
            return f"contraindication:{ci.condition_code}"
        if ci.action == "limit_low_irritancy" and p.max_irritancy >= 3:
            return f"contraindication:{ci.condition_code}"
    if not ctx.triage.allow_actives:
        if p.category not in BASIC_CATEGORIES or p.actives:
            return "actives_not_allowed"
    if intake.skin_type not in p.suitable_skin_types and "all" not in p.suitable_skin_types:
        return "skin_type"
    return None


def passes_hard_filters(p: Product, ctx: Context) -> bool:
    return exclusion_reason(p, ctx) is None


# ----- Scoring ----------------------------------------------------------------

def concern_weights(ctx: Context) -> dict[str, float]:
    w: dict[str, float] = {}
    inf = ctx.inference
    if inf is not None and inf.quality_pass:
        for code in LABELS:
            lab = inf.labels.get(code)
            if lab is None:
                continue
            if lab.present:
                w[code] = float(GRADE_WEIGHT[lab.grade] or 1)
            elif lab.uncertain and ctx.intake.self_severity(code):
                w[code] = 1.0
    for c in ctx.intake.concerns:
        if c.code not in LABELS:  # dryness, oiliness: self-report only
            w[c.code] = float(max(1, min(3, c.self_severity)))
    return w


def _current_active_ids(ctx: Context) -> frozenset[str]:
    ids: set[str] = set()
    for p in ctx.catalog:
        if p.id in ctx.intake.current_product_ids:
            ids |= {i.id for i in p.actives}
    return frozenset(ids)


def score(p: Product, ctx: Context, weights: dict[str, float] | None = None) -> float:
    weights = concern_weights(ctx) if weights is None else weights
    benefit = 0.0
    for ing in p.ingredients:
        for concern, bw in ing.benefits:
            benefit += bw * weights.get(concern, 0.0)
    current = _current_active_ids(ctx)
    new_actives = sum(1 for i in p.actives if i.id not in current)
    return round(benefit - 0.5 * p.max_irritancy - 0.2 * new_actives, 6)


def _sort_key(p: Product, s: float):
    return (-s, not p.stocked_by_iconic, p.price_php, p.id)


# ----- Conflicts --------------------------------------------------------------

def _pair_ok(a: RoutineItem, b: RoutineItem, rule: ConflictRule) -> bool:
    """True if two placed items satisfy `rule` as placed."""
    if rule.resolution == "block":
        return False
    if rule.resolution == "split_am_pm":
        if rule.scope == "same_application":
            return a.time_of_day != b.time_of_day
        return False
    if rule.resolution == "alternate_nights":
        return (
            a.time_of_day == b.time_of_day == "pm"
            and a.frequency == b.frequency == "alternate_nights"
        )
    return False


def _conflicts(a: Product, b: Product, rules: RuleSet) -> list[ConflictRule]:
    return [r for r in rules.conflicts if r.matches(a.families, b.families)]


def _try_place(items: list[RoutineItem], cand: RoutineItem, rules: RuleSet) -> list[RoutineItem] | None:
    """Place `cand`, resolving conflicts by rule. Returns new items or None."""
    if cand.time_of_day == "am" and cand.product.photosensitizing:
        return None
    out = list(items)
    cand_freq = cand.frequency
    for i, x in enumerate(out):
        if x.product.id == cand.product.id:
            continue
        for rule in _conflicts(x.product, cand.product, rules):
            if rule.resolution == "block":
                return None
            if rule.resolution == "split_am_pm":
                if x.time_of_day == cand.time_of_day:
                    return None
            elif rule.resolution == "alternate_nights":
                if not (x.time_of_day == cand.time_of_day == "pm"):
                    return None
                if x.slot != "treatment":  # never put a basic step on alternate nights
                    return None
                out[i] = replace(x, frequency="alternate_nights")
                cand_freq = "alternate_nights"
    out.append(replace(cand, frequency=cand_freq))
    return out


# ----- Explanations -----------------------------------------------------------

_ACRONYMS = {"pca", "np", "spf"}


def _display(inci: str) -> str:
    return " ".join(w.upper() if w in _ACRONYMS else w.capitalize() for w in inci.split())


def _why(p: Product, slot: str, weights: dict[str, float], skin_type: str) -> str:
    if slot == "sunscreen":
        spf = f"SPF {p.spf}" if p.spf else "Broad-spectrum"
        return f"{spf} {p.pa_rating or ''}".strip() + " daily protection; reapply every 2 hours outdoors."
    best: tuple[float, str, str] | None = None
    for ing in p.ingredients:
        for concern, bw in ing.benefits:
            val = bw * weights.get(concern, 0.0)
            if val > 0 and (best is None or val > best[0] or (val == best[0] and ing.inci_name < best[1])):
                best = (val, ing.inci_name, concern)
    if best is not None:
        return f"{_display(best[1])}, chosen for {CONCERN_PHRASES.get(best[2], best[2])}."
    if slot == "cleanser":
        return f"Gentle cleanser suited to {skin_type} skin."
    if slot == "moisturizer":
        return f"Moisturizer suited to {skin_type} skin; supports the skin barrier."
    return "Suited to your skin type."


# ----- Assembly ---------------------------------------------------------------

def _hash_inputs(ctx: Context) -> str:
    inf = ctx.inference
    payload = {
        "recommender": RECOMMENDER_VERSION,
        "rule_set": ctx.rules.version,
        "triage": [ctx.triage.route, list(ctx.triage.reasons), ctx.triage.allow_actives],
        "labels": None if inf is None else {
            k: [round(v.p, 6), v.present, v.grade, v.uncertain] for k, v in sorted(inf.labels.items())
        },
        "intake": {
            "concerns": sorted([c.code, c.self_severity, c.duration_weeks] for c in ctx.intake.concerns),
            "skin_type": ctx.intake.skin_type,
            "preg": ctx.intake.pregnant_or_breastfeeding,
            "iso": ctx.intake.on_isotretinoin,
            "rx": ctx.intake.current_rx_topicals,
            "allergen_ids": sorted(ctx.intake.allergen_ingredient_ids),
            "allergen_fams": sorted(ctx.intake.allergen_families),
            "reacted": sorted(ctx.intake.reacted_product_ids),
            "current": sorted(ctx.intake.current_product_ids),
            "exp": ctx.intake.uses_actives_without_reaction,
        },
        "catalog": sorted([p.id, p.is_listed] for p in ctx.catalog),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def _pick(pool: list[Product], categories: tuple[str, ...], ctx: Context, weights, predicate=lambda p: True):
    cands = [p for p in pool if p.category in categories and predicate(p)]
    return sorted(cands, key=lambda p: _sort_key(p, score(p, ctx, weights)))


def _sunscreen_ok(p: Product) -> bool:
    return (p.spf or 0) >= MIN_SPF and (p.pa_rating in PA_OK)


def build_routine(ctx: Context) -> Routine:
    if ctx.triage.route == "urgent_care":
        raise NoSafeProduct("urgent_care")  # no routine by design

    weights = concern_weights(ctx)
    pool = [p for p in sorted(ctx.catalog, key=lambda p: p.id) if passes_hard_filters(p, ctx)]
    items: list[RoutineItem] = []
    notes: list[str] = []

    def place_basic(slot: str, cats: tuple[str, ...], tods: tuple[str, ...], predicate=lambda p: True):
        nonlocal items
        for p in _pick(pool, cats, ctx, weights, predicate):
            trial = items
            ok = True
            for tod in tods:
                cand = RoutineItem(tod, 0, slot, p, "daily", _why(p, slot, weights, ctx.intake.skin_type),
                                   patch_test=bool(p.actives))
                placed = _try_place(trial, cand, ctx.rules)
                if placed is None:
                    ok = False
                    break
                trial = placed
            if ok:
                items = trial
                return
        raise NoSafeProduct(slot)

    place_basic("cleanser", ("cleanser",), ("am", "pm"))
    place_basic("moisturizer", ("moisturizer",), ("am", "pm"))
    place_basic("sunscreen", ("sunscreen",), ("am",), _sunscreen_ok)

    # Optional treatments.
    max_treat = 0
    if ctx.triage.allow_actives:
        max_treat = 2 if ctx.intake.uses_actives_without_reaction else 1
    current_actives = _current_active_ids(ctx)
    placed_treat = 0
    used_tods: dict[str, int] = {"am": 0, "pm": 0}
    for p in _pick(pool, TREATMENT_CATEGORIES, ctx, weights):
        if placed_treat >= max_treat:
            break
        if score(p, ctx, weights) <= 0:
            continue  # only add a treatment that addresses a detected concern
        prefer = ("pm", "am") if p.photosensitizing else ("am", "pm")
        for tod in prefer:
            if used_tods[tod] >= 1 and tod == "am":
                continue
            new_active = any(i.id not in current_actives for i in p.actives)
            cand = RoutineItem(tod, 0, "treatment", p, "daily", _why(p, "treatment", weights, ctx.intake.skin_type),
                               patch_test=new_active)
            # A second PM treatment is only allowed as an alternating pair.
            if tod == "pm" and used_tods["pm"] >= 1:
                trial = _try_place(items, replace(cand, frequency="alternate_nights"), ctx.rules)
                if trial is not None:
                    pm_treats = [i for i in trial if i.slot == "treatment" and i.time_of_day == "pm"]
                    if not all(i.frequency == "alternate_nights" for i in pm_treats):
                        trial = None
            else:
                trial = _try_place(items, cand, ctx.rules)
            if trial is not None:
                items = trial
                placed_treat += 1
                used_tods[tod] += 1
                break

    if any(i.patch_test for i in items):
        notes.append("Patch-test each new product on the side of the neck for 3 nights before using it on the face.")
        notes.append("Introduce one new product every 2 weeks.")
    if any(i.frequency == "alternate_nights" for i in items):
        notes.append("Products marked 'alternate nights' are used on different evenings, never together.")

    # Step order.
    order = {"cleanser": 1, "treatment": 2, "moisturizer": 4, "sunscreen": 5}
    numbered: list[RoutineItem] = []
    for tod in ("am", "pm"):
        here = sorted((i for i in items if i.time_of_day == tod),
                      key=lambda i: (order[i.slot], i.product.id))
        for n, i in enumerate(here, start=1):
            numbered.append(replace(i, step_order=n))

    routine = Routine(items=tuple(numbered), rule_set_version=ctx.rules.version,
                      input_hash=_hash_inputs(ctx), notes=tuple(notes))
    final_safety_check(routine, ctx)
    return routine


def final_safety_check(routine: Routine, ctx: Context) -> None:
    """Re-run every hard filter and conflict rule on the assembled routine."""
    items = routine.items
    for it in items:
        why = exclusion_reason(it.product, ctx)
        if why is not None:
            raise UnsafeRoutine(f"{it.product.id} fails hard filter: {why}")
        if it.time_of_day == "am" and it.product.photosensitizing:
            raise UnsafeRoutine(f"{it.product.id} is photosensitizing in the AM")
    for n, a in enumerate(items):
        for b in items[n + 1:]:
            if a.product.id == b.product.id:
                continue
            for rule in _conflicts(a.product, b.product, ctx.rules):
                if not _pair_ok(a, b, rule):
                    raise UnsafeRoutine(f"unresolved conflict {rule.family_a}+{rule.family_b} "
                                        f"between {a.product.id} and {b.product.id}")
    am = routine.at("am")
    if ctx.triage.route != "urgent_care" and not any(i.slot == "sunscreen" and _sunscreen_ok(i.product) for i in am):
        raise UnsafeRoutine("AM routine has no qualifying sunscreen")
