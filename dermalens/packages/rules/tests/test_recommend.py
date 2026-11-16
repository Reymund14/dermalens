from dataclasses import replace

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from dermalens_rules import (
    Context, Intake, NoSafeProduct, RedFlag, ReportedConcern, build_routine, exclusion_reason, triage,
)
from dermalens_rules.recommend import _conflicts, _pair_ok
from dermalens_rules.seed import INGREDIENTS, RULES, sample_products

from .conftest import make_inference

CATALOG = sample_products()


def run(intake=Intake(), grades=None, **kw):
    inference = make_inference(grades or {}, **kw)
    t = triage(intake, inference)
    return build_routine(Context(intake=intake, triage=t, inference=inference, catalog=CATALOG, rules=RULES)), t


def ids(routine, tod=None):
    return [i.product.id for i in routine.items if tod is None or i.time_of_day == tod]


def test_basic_shape_and_sunscreen():
    r, _ = run(Intake(skin_type="normal"), {"acne": "mild"})
    am, pm = r.at("am"), r.at("pm")
    assert [i.slot for i in am][0] == "cleanser" and am[-1].slot == "sunscreen"
    assert am[-1].product.spf >= 30 and am[-1].product.pa_rating in ("PA+++", "PA++++")
    assert [i.slot for i in pm][0] == "cleanser" and pm[-1].slot == "moisturizer"
    assert "p-ss-weak" not in ids(r)


def test_unverified_product_never_used():
    for grades in ({"hyperpigmentation": "moderate"}, {"hyperpigmentation": "mild"}):
        r, _ = run(Intake(), grades)
        assert "p-se-unverified" not in ids(r)


def test_allergen_family_excluded():
    intake = Intake(skin_type="oily", allergen_families=frozenset({"bha"}))
    r, _ = run(intake, {"acne": "moderate"})
    for it in r.items:
        assert "bha" not in it.product.families


def test_allergen_ingredient_excluded():
    intake = Intake(skin_type="normal", allergen_ingredient_ids=frozenset({"niacinamide"}))
    r, _ = run(intake, {"hyperpigmentation": "moderate"})
    for it in r.items:
        assert "niacinamide" not in it.product.ingredient_ids


def test_pregnancy_excludes_retinoids_and_leave_on_bha():
    intake = Intake(skin_type="oily", pregnant_or_breastfeeding=True)
    r, _ = run(intake, {"texture": "moderate", "acne": "mild"})
    for it in r.items:
        assert "retinoids" not in it.product.families
        if "bha" in it.product.families:
            assert it.product.category == "cleanser"


def test_isotretinoin_excludes_exfoliants():
    intake = Intake(skin_type="oily", on_isotretinoin=True)
    r, _ = run(intake, {"texture": "moderate"})
    for it in r.items:
        assert not it.product.families & {"aha", "bha", "retinoids", "physical_scrub"}


def test_sensitive_skin_no_fragrance_or_high_irritancy():
    intake = Intake(skin_type="sensitive")
    r, _ = run(intake, {"erythema": "mild"})
    for it in r.items:
        assert "fragrance" not in it.product.families
        assert it.product.max_irritancy < 3


def test_dermatologist_route_gives_basics_only():
    intake = Intake(red_flags_true=(RedFlag("changing_mole", "dermatologist"),))
    r, t = run(intake, {"acne": "moderate"})
    assert t.route == "dermatologist"
    assert {i.slot for i in r.items} == {"cleanser", "moisturizer", "sunscreen"}
    assert all(not i.product.actives for i in r.items)


def test_urgent_route_gives_no_routine():
    intake = Intake(red_flags_true=(RedFlag("rapid_swelling", "urgent_care"),))
    with pytest.raises(NoSafeProduct):
        run(intake)


def test_photosensitizing_goes_to_pm():
    r, _ = run(Intake(skin_type="normal"), {"texture": "moderate"})
    for it in r.items:
        if it.product.photosensitizing:
            assert it.time_of_day == "pm"


def test_retinoid_and_acid_alternate_nights_for_experienced_user():
    intake = Intake(skin_type="combination", uses_actives_without_reaction=True,
                    concerns=(ReportedConcern("texture", 3, 4),))
    r, _ = run(intake, {"texture": "moderate", "hyperpigmentation": "mild"})
    pm_treat = [i for i in r.at("pm") if i.slot == "treatment"]
    fams = [i.product.families for i in pm_treat]
    if len(pm_treat) == 2 and any("retinoids" in f for f in fams):
        assert all(i.frequency == "alternate_nights" for i in pm_treat)


def test_reacted_product_and_its_actives_excluded():
    intake = Intake(skin_type="normal", reacted_product_ids=frozenset({"p-se-niacinamide"}),
                    current_product_ids=frozenset({"p-se-niacinamide"}))
    r, _ = run(intake, {"hyperpigmentation": "moderate"})
    for it in r.items:
        assert "niacinamide" not in it.product.ingredient_ids


def test_patch_test_flag_on_new_actives():
    r, _ = run(Intake(skin_type="normal"), {"hyperpigmentation": "moderate"})
    treat = [i for i in r.items if i.slot == "treatment"]
    assert treat and all(i.patch_test for i in treat)
    assert any("Patch-test" in n for n in r.notes)


def test_why_text_present():
    r, _ = run(Intake(skin_type="oily"), {"acne": "moderate"})
    assert all(i.why for i in r.items)


# ----- Property-based invariants ----------------------------------------------

FAMS = ["fragrance", "essential_oils", "retinoids", "aha", "bha", "vitamin_c", "physical_scrub", "lanolin", "parabens"]
GRADE = st.sampled_from(["none", "mild", "moderate", "marked"])

profiles = st.builds(
    lambda skin, preg, iso, rx, fams, ings, reacted, exp, g, refer, flags: (
        Intake(skin_type=skin, pregnant_or_breastfeeding=preg, on_isotretinoin=iso, current_rx_topicals=rx,
               allergen_families=frozenset(fams), allergen_ingredient_ids=frozenset(ings),
               reacted_product_ids=frozenset(reacted), uses_actives_without_reaction=exp,
               red_flags_true=tuple(RedFlag(c, "dermatologist") for c in flags)),
        g, refer),
    st.sampled_from(["dry", "oily", "combination", "normal", "sensitive"]),
    st.booleans(), st.booleans(), st.booleans(),
    st.lists(st.sampled_from(FAMS), max_size=3, unique=True),
    st.lists(st.sampled_from(sorted(INGREDIENTS)), max_size=3, unique=True),
    st.lists(st.sampled_from([p.id for p in CATALOG]), max_size=2, unique=True),
    st.booleans(),
    st.fixed_dictionaries({"acne": GRADE, "hyperpigmentation": GRADE, "erythema": GRADE, "texture": GRADE}),
    st.sampled_from([0.0, 0.1, 0.5]),
    st.lists(st.sampled_from(["changing_mole"]), max_size=1),
)

catalog_subsets = st.lists(st.sampled_from(list(CATALOG)), min_size=3, unique_by=lambda p: p.id).map(tuple)


@settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(profiles, catalog_subsets)
def test_invariants(profile, catalog):
    intake, grades, refer = profile
    inference = make_inference(grades, refer_out=refer)
    t = triage(intake, inference)
    ctx = Context(intake=intake, triage=t, inference=inference, catalog=catalog, rules=RULES)
    try:
        r1 = build_routine(ctx)
    except NoSafeProduct:
        return  # surfaced to the user as "ask ICONIC staff"; never an unsafe routine
    # 1. No product contains a declared allergen or family member, or fails any hard filter.
    for it in r1.items:
        assert not (it.product.ingredient_ids & intake.allergen_ingredient_ids)
        assert not (it.product.families & intake.allergen_families)
        assert exclusion_reason(it.product, ctx) is None
    # 2. No unresolved conflict.
    for n, a in enumerate(r1.items):
        for b in r1.items[n + 1:]:
            if a.product.id != b.product.id:
                for rule in _conflicts(a.product, b.product, RULES):
                    assert _pair_ok(a, b, rule)
    # 3. Same input, same output.
    r2 = build_routine(replace(ctx, catalog=tuple(reversed(catalog))))
    assert r2 == r1  # catalog order must not matter
    assert build_routine(ctx) == r1
