"""Reviewed copy table (vocabulary lock).

Every user-facing string about results comes from here. Findings describe
visible features, never conditions; `tests/test_copy.py` fails the build if a
forbidden word slips into any string below.
"""
from __future__ import annotations

COPY_VERSION = "copy-1.0.0"

BOUNDARY_STATEMENT = (
    "DermaLens provides general skincare information and a visual pre-screening of cosmetic "
    "skin concerns. It does not diagnose, treat, or rule out any disease. Results are not a "
    "substitute for an examination by a licensed physician. If you have a changing mole, a sore "
    "that does not heal, pain, bleeding, rapid spreading, fever, or any concern about your "
    "health, consult a board-certified dermatologist."
)

# Words that may never appear as findings, reasons or route copy. The boundary
# statement itself is exempt because it must say what the app does not do.
FORBIDDEN_WORDS = (
    "diagnosis", "diagnose", "disease", "cure", "rosacea", "melasma", "eczema",
    "psoriasis", "dermatitis", "cancer", "melanoma", "infection", "fungal",
)

CONCERN_NAMES = {
    "acne": "Breakouts and clogged pores",
    "hyperpigmentation": "Uneven tone and dark spots",
    "erythema": "Redness",
    "texture": "Uneven texture and visible pores",
    "dryness": "Dryness",
    "oiliness": "Oiliness and shine",
}

CONCERN_PHRASES = {  # used in "why this product" lines
    "acne": "breakouts and clogged pores",
    "hyperpigmentation": "uneven tone",
    "erythema": "visible redness",
    "texture": "uneven texture",
    "dryness": "dryness",
    "oiliness": "oiliness",
}

GRADE_NAMES = {"none": "Not seen", "mild": "Mild", "moderate": "Moderate", "marked": "Marked"}

ROUTES = {
    "urgent_care": {
        "title": "Please seek medical care promptly",
        "body": "What you described needs a doctor today. Go to an emergency room or see a physician as soon as you can. "
                "DermaLens will not suggest a routine for this.",
        "tone": "urgent",
        "cta": "Find urgent care",
    },
    "dermatologist": {
        "title": "Please see a board-certified dermatologist",
        "body": "This app cannot assess what you described or what it saw. A dermatologist can examine your skin in person. "
                "Until then, keep to gentle basics: a mild cleanser, a moisturizer and sunscreen.",
        "tone": "caution",
        "cta": "Find a dermatologist",
    },
    "iconic_clinic": {
        "title": "A consultation at ICONIC Aesthetic Clinic may help",
        "body": "Your photos show cosmetic concerns that may benefit from a professional consultation. "
                "You can share a pre-screening summary with ICONIC staff before your visit.",
        "tone": "info",
        "cta": "Book with ICONIC",
    },
    "self_care": {
        "title": "An at-home routine is a reasonable start",
        "body": "Your photos show mild cosmetic concerns or none. Start the routine below and check again in 6 to 8 weeks. "
                "You can still book a consultation at ICONIC at any time.",
        "tone": "ok",
        "cta": "See my routine",
    },
}

REASON_TEXT = {
    "quality:failed": "The photos could not be checked reliably, even after a retake.",
    "model:refer_out": "The photos show something this app is not designed to assess.",
    "model:ood": "The photos look different from what this app was trained on.",
    "severity:acne": "Breakouts look marked, or have lasted more than 12 weeks.",
    "severity:hyperpigmentation": "Uneven tone looks marked; in-clinic options need an in-person assessment.",
    "severity:erythema": "Redness looks marked; in-clinic options need an in-person assessment.",
    "severity:texture": "Uneven texture looks marked; in-clinic options need an in-person assessment.",
    "cosmetic:moderate_or_multiple": "One concern looks moderate, or several concerns are visible.",
    "cosmetic:mild_or_none": "Only mild concerns, or none, are visible.",
    "model:uncertain_label": "At least one result is uncertain; clinic staff will see it flagged.",
}

RED_FLAG_REASON_PREFIX = "You told us: "


def reason_text(code: str, red_flag_questions: dict[str, str] | None = None) -> str:
    if code.startswith("redflag:"):
        flag = code.split(":", 1)[1]
        q = (red_flag_questions or {}).get(flag, flag.replace("_", " "))
        return RED_FLAG_REASON_PREFIX + q.rstrip("?").lower() + "."
    return REASON_TEXT.get(code, code)


def all_result_strings() -> list[str]:
    out: list[str] = []
    out += CONCERN_NAMES.values()
    out += CONCERN_PHRASES.values()
    out += GRADE_NAMES.values()
    out += REASON_TEXT.values()
    for r in ROUTES.values():
        out += [r["title"], r["body"], r["cta"]]
    return out
