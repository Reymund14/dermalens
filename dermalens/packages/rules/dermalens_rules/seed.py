"""Seed data: concerns, red flags, ingredient families, ingredients, rules and a
SAMPLE product catalog.

IMPORTANT: the products below are placeholders for development and testing.
Their brands are fictional and their notification numbers are of the form
"SAMPLE-..." on purpose. Before launch, replace them with real products whose
Philippine FDA cosmetic notification has been looked up on the FDA
verification portal, with the evidence saved (see README, "Catalog").
Benzoyl peroxide and other actives that are often registered as drugs in the
Philippines are kept as rule families but no sample product contains them.
"""
from __future__ import annotations

from .models import ConflictRule, Contraindication, Ingredient, Product, RuleSet

RULE_SET_VERSION = "rules-1.0.0"

CONCERNS = [
    # code, display name, is a model label
    ("acne", "Breakouts and clogged pores", True),
    ("hyperpigmentation", "Uneven tone and dark spots", True),
    ("erythema", "Redness", True),
    ("texture", "Uneven texture and visible pores", True),
    ("dryness", "Dryness", False),
    ("oiliness", "Oiliness and shine", False),
]

RED_FLAGS = [
    # code, question, route
    ("fever_spreading_rash", "Do you have a fever together with a rash that is spreading?", "urgent_care"),
    ("rapid_swelling", "Is your face, lips or eyes swelling quickly?", "urgent_care"),
    ("widespread_blistering", "Do you have blistering or peeling skin over a large area?", "urgent_care"),
    ("severe_pain", "Is any area of your skin severely painful?", "urgent_care"),
    ("changing_mole", "Do you have a mole or spot that is new, changing, bleeding, itching or irregular?", "dermatologist"),
    ("non_healing_sore", "Do you have a sore that has not healed in 3 weeks?", "dermatologist"),
    ("deep_painful_lumps", "Do you have painful, deep lumps or cysts under the skin?", "dermatologist"),
    ("scarring_breakouts", "Are your breakouts leaving pitted or raised scars?", "dermatologist"),
    ("hair_loss_with_rash", "Have you had sudden hair loss together with a rash?", "dermatologist"),
    ("rx_new_reaction", "Are you on prescription acne medicine and having a new skin reaction?", "dermatologist"),
    ("long_lasting_despite_care", "Have your skin symptoms lasted more than 12 weeks despite care?", "dermatologist"),
]

FAMILIES = [
    ("fragrance", "Fragrance"),
    ("essential_oils", "Essential oils"),
    ("retinoids", "Retinoids (retinol, retinyl esters)"),
    ("aha", "AHA exfoliating acids (glycolic, lactic)"),
    ("bha", "BHA (salicylic acid)"),
    ("benzoyl_peroxide", "Benzoyl peroxide"),
    ("vitamin_c", "L-ascorbic acid (vitamin C)"),
    ("physical_scrub", "Physical scrubs"),
    ("lanolin", "Lanolin"),
    ("parabens", "Parabens"),
]


def _ing(id, inci, fams=(), irr=0, active=False, photo=False, preg=False, benefits=()):
    return Ingredient(id=id, inci_name=inci, families=frozenset(fams), irritancy_level=irr, is_active=active,
                      photosensitizing=photo, pregnancy_avoid=preg, benefits=tuple(benefits))


INGREDIENTS = {i.id: i for i in [
    _ing("water", "aqua"),
    _ing("glycerin", "glycerin", benefits=[("dryness", 0.3)]),
    _ing("ceramide_np", "ceramide np", benefits=[("dryness", 0.5), ("erythema", 0.2)]),
    _ing("sodium_hyaluronate", "sodium hyaluronate", benefits=[("dryness", 0.4)]),
    _ing("squalane", "squalane", benefits=[("dryness", 0.5)]),
    _ing("shea_butter", "butyrospermum parkii butter", benefits=[("dryness", 0.4)]),
    _ing("dimethicone", "dimethicone"),
    _ing("phenoxyethanol", "phenoxyethanol"),
    _ing("panthenol", "panthenol", benefits=[("erythema", 0.3), ("dryness", 0.3)]),
    _ing("allantoin", "allantoin", benefits=[("erythema", 0.3)]),
    _ing("centella", "centella asiatica extract", benefits=[("erythema", 0.5)]),
    _ing("green_tea", "camellia sinensis leaf extract", benefits=[("erythema", 0.3), ("oiliness", 0.2)]),
    _ing("zinc_pca", "zinc pca", benefits=[("oiliness", 0.5), ("acne", 0.2)]),
    _ing("niacinamide", "niacinamide", active=True,
         benefits=[("hyperpigmentation", 0.6), ("oiliness", 0.4), ("texture", 0.3), ("erythema", 0.2), ("acne", 0.3)]),
    _ing("salicylic_acid", "salicylic acid", fams=["bha"], irr=2, active=True,
         benefits=[("acne", 0.8), ("texture", 0.5), ("oiliness", 0.4)]),
    _ing("glycolic_acid", "glycolic acid", fams=["aha"], irr=2, active=True, photo=True,
         benefits=[("texture", 0.8), ("hyperpigmentation", 0.5)]),
    _ing("lactic_acid", "lactic acid", fams=["aha"], irr=1, active=True, photo=True,
         benefits=[("texture", 0.6), ("hyperpigmentation", 0.4), ("dryness", 0.2)]),
    _ing("retinol", "retinol", fams=["retinoids"], irr=2, active=True, photo=True, preg=True,
         benefits=[("texture", 0.8), ("acne", 0.5), ("hyperpigmentation", 0.4)]),
    _ing("retinyl_palmitate", "retinyl palmitate", fams=["retinoids"], irr=1, active=True, photo=True, preg=True,
         benefits=[("texture", 0.4)]),
    _ing("ascorbic_acid", "ascorbic acid", fams=["vitamin_c"], irr=1, active=True,
         benefits=[("hyperpigmentation", 0.7)]),
    _ing("tranexamic_acid", "tranexamic acid", active=True, benefits=[("hyperpigmentation", 0.6)]),
    _ing("alpha_arbutin", "alpha-arbutin", active=True, benefits=[("hyperpigmentation", 0.6)]),
    _ing("zinc_oxide", "zinc oxide"),
    _ing("titanium_dioxide", "titanium dioxide"),
    _ing("octinoxate", "ethylhexyl methoxycinnamate"),
    _ing("bemotrizinol", "bis-ethylhexyloxyphenol methoxyphenyl triazine"),
    _ing("parfum", "parfum", fams=["fragrance"], irr=1),
    _ing("linalool", "linalool", fams=["fragrance"], irr=1),
    _ing("lavender_oil", "lavandula angustifolia oil", fams=["essential_oils"], irr=2),
    _ing("tea_tree_oil", "melaleuca alternifolia leaf oil", fams=["essential_oils"], irr=2, benefits=[("acne", 0.3)]),
    _ing("lanolin", "lanolin", fams=["lanolin"]),
    _ing("methylparaben", "methylparaben", fams=["parabens"]),
    _ing("jojoba_beads", "hydrogenated jojoba oil (beads)", fams=["physical_scrub"], irr=1, benefits=[("texture", 0.3)]),
]}

SYNONYMS = {
    "fragrance": "parfum", "perfume": "parfum", "parfum": "parfum",
    "vitamin a": "retinol", "retinol": "retinol", "vitamin c": "ascorbic_acid", "l-ascorbic acid": "ascorbic_acid",
    "vitamin b3": "niacinamide", "niacinamide": "niacinamide", "bha": "salicylic_acid", "salicylic acid": "salicylic_acid",
    "aha": "glycolic_acid", "glycolic acid": "glycolic_acid", "lactic acid": "lactic_acid", "lanolin": "lanolin",
    "paraben": "methylparaben", "methylparaben": "methylparaben", "tea tree": "tea_tree_oil", "tea tree oil": "tea_tree_oil",
    "lavender": "lavender_oil", "lavender oil": "lavender_oil", "zinc oxide": "zinc_oxide", "arbutin": "alpha_arbutin",
    "tranexamic acid": "tranexamic_acid", "centella": "centella", "cica": "centella", "hyaluronic acid": "sodium_hyaluronate",
}

CONFLICTS = (
    ConflictRule("retinoids", "aha", "same_routine", "alternate_nights", "Additive irritation and barrier damage"),
    ConflictRule("retinoids", "bha", "same_routine", "alternate_nights", "Additive irritation and barrier damage"),
    ConflictRule("retinoids", "benzoyl_peroxide", "same_application", "split_am_pm",
                 "Irritation; benzoyl peroxide can degrade some retinoids"),
    ConflictRule("aha", "bha", "same_day", "block", "Over-exfoliation; keep one exfoliant"),
    ConflictRule("aha", "physical_scrub", "same_day", "block", "Over-exfoliation; keep one exfoliant"),
    ConflictRule("bha", "physical_scrub", "same_day", "block", "Over-exfoliation; keep one exfoliant"),
    ConflictRule("vitamin_c", "aha", "same_application", "split_am_pm", "Low-pH stacking raises irritation"),
    ConflictRule("vitamin_c", "bha", "same_application", "split_am_pm", "Low-pH stacking raises irritation"),
    ConflictRule("benzoyl_peroxide", "vitamin_c", "same_application", "split_am_pm", "Oxidation of vitamin C"),
)

CONTRAINDICATIONS = (
    Contraindication("pregnancy", "retinoids", None, "exclude"),
    Contraindication("pregnancy", "bha", None, "limit_wash_off"),
    *(Contraindication(cond, fam, None, "exclude")
      for cond in ("isotretinoin", "rx_topical")
      for fam in ("aha", "bha", "retinoids", "benzoyl_peroxide", "physical_scrub")),
    Contraindication("sensitive_skin", "fragrance", None, "exclude"),
    Contraindication("sensitive_skin", "essential_oils", None, "exclude"),
    Contraindication("sensitive_skin", None, None, "limit_low_irritancy"),
)

RULES = RuleSet(version=RULE_SET_VERSION, conflicts=CONFLICTS, contraindications=CONTRAINDICATIONS)

ALL = ("dry", "oily", "combination", "normal", "sensitive")
NOT_SENS = ("dry", "oily", "combination", "normal")
OILY = ("oily", "combination", "normal")
DRY = ("dry", "normal", "sensitive", "combination")

_P = [
    # id, name, category, skin types, ingredients, spf, pa, price, stocked, listed
    ("p-cl-gentle", "Gentle Hydrating Cleanser", "cleanser", ALL,
     ["water", "glycerin", "ceramide_np", "panthenol", "phenoxyethanol"], None, None, 450, True, True),
    ("p-cl-gel", "Balancing Gel Cleanser", "cleanser", OILY,
     ["water", "glycerin", "zinc_pca", "green_tea", "phenoxyethanol"], None, None, 380, False, True),
    ("p-cl-bha", "Clarifying BHA Wash 0.5%", "cleanser", OILY,
     ["water", "glycerin", "salicylic_acid", "zinc_pca", "phenoxyethanol"], None, None, 520, True, True),
    ("p-cl-scented", "Rose Cream Cleanser", "cleanser", NOT_SENS,
     ["water", "glycerin", "shea_butter", "parfum", "linalool"], None, None, 300, False, True),
    ("p-mo-barrier", "Barrier Repair Cream", "moisturizer", DRY,
     ["water", "glycerin", "ceramide_np", "squalane", "panthenol", "dimethicone"], None, None, 690, True, True),
    ("p-mo-gel", "Oil-Free Water Gel", "moisturizer", OILY,
     ["water", "glycerin", "sodium_hyaluronate", "niacinamide", "phenoxyethanol"], None, None, 560, False, True),
    ("p-mo-cica", "Calming Cica Lotion", "moisturizer", ALL,
     ["water", "glycerin", "centella", "allantoin", "panthenol"], None, None, 610, True, True),
    ("p-mo-lanolin", "Rich Lanolin Balm", "moisturizer", ("dry",),
     ["lanolin", "shea_butter", "methylparaben"], None, None, 350, False, True),
    ("p-ss-mineral", "Mineral Sunscreen SPF 50", "sunscreen", ALL,
     ["water", "zinc_oxide", "titanium_dioxide", "glycerin", "dimethicone"], 50, "PA++++", 850, True, True),
    ("p-ss-light", "Light Fluid Sunscreen SPF 50", "sunscreen", OILY,
     ["water", "octinoxate", "bemotrizinol", "niacinamide", "phenoxyethanol"], 50, "PA++++", 720, False, True),
    ("p-ss-weak", "Daily Tinted Moisturizer SPF 15", "sunscreen", ALL,
     ["water", "octinoxate", "glycerin"], 15, "PA+", 400, False, True),
    ("p-se-niacinamide", "Niacinamide 5% Serum", "serum", ALL,
     ["water", "niacinamide", "zinc_pca", "glycerin"], None, None, 650, True, True),
    ("p-se-vitc", "Vitamin C 10% Serum", "serum", NOT_SENS,
     ["water", "ascorbic_acid", "glycerin", "phenoxyethanol"], None, None, 980, True, True),
    ("p-se-txa", "Tranexamic + Arbutin Serum", "serum", ALL,
     ["water", "tranexamic_acid", "alpha_arbutin", "niacinamide", "glycerin"], None, None, 890, False, True),
    ("p-se-retinol", "Retinol 0.3% Night Serum", "treatment", NOT_SENS,
     ["water", "retinol", "squalane", "glycerin"], None, None, 1100, True, True),
    ("p-ex-bha", "BHA 2% Liquid Exfoliant", "exfoliant", OILY,
     ["water", "salicylic_acid", "green_tea", "glycerin"], None, None, 780, False, True),
    ("p-ex-aha", "Glycolic 7% Toning Solution", "exfoliant", NOT_SENS,
     ["water", "glycolic_acid", "glycerin", "panthenol"], None, None, 720, True, True),
    ("p-ex-lactic", "Lactic 5% Gentle Peel", "exfoliant", ("dry", "normal", "combination"),
     ["water", "lactic_acid", "sodium_hyaluronate"], None, None, 690, False, True),
    ("p-se-cica", "Centella Soothing Ampoule", "serum", ALL,
     ["water", "centella", "panthenol", "allantoin", "green_tea"], None, None, 590, True, True),
    ("p-se-teatree", "Tea Tree Spot Gel", "treatment", OILY,
     ["water", "tea_tree_oil", "lavender_oil", "zinc_pca"], None, None, 320, False, True),
    ("p-ex-scrub", "Smoothing Jojoba Scrub", "exfoliant", NOT_SENS,
     ["water", "glycerin", "jojoba_beads", "parfum"], None, None, 410, False, True),
    ("p-se-unverified", "Brightening Essence (verification lapsed)", "serum", ALL,
     ["water", "niacinamide", "alpha_arbutin"], None, None, 500, False, False),
]


def sample_products() -> tuple[Product, ...]:
    out = []
    for n, (pid, name, cat, skin, ings, spf, pa, price, stocked, listed) in enumerate(_P, start=1):
        out.append(Product(
            id=pid, brand="Sample Catalog", name=name, category=cat, suitable_skin_types=frozenset(skin),
            ingredients=tuple(INGREDIENTS[i] for i in ings), spf=spf, pa_rating=pa, price_php=float(price),
            stocked_by_iconic=stocked, is_listed=listed,
            fda_notification_no=f"SAMPLE-{n:04d}" if listed else None,
        ))
    return tuple(out)
