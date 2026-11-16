"""Fixed-order triage cascade (rule set v1).

The first rule that fires sets the route; every rule that fired is recorded.
Intake red flags are evaluated before the model is consulted, so a confident
model can never talk the app out of a referral.
"""
from __future__ import annotations

from .models import Inference, Intake, TriageResult

RULE_SET_VERSION = "triage-1.0.0"

# Lower number = higher priority. Used only to order intake red flags so an
# urgent flag always wins over a dermatologist flag regardless of answer order.
_ROUTE_PRIORITY = {"urgent_care": 0, "dermatologist": 1, "iconic_clinic": 2, "self_care": 3}


def triage(intake: Intake, inference: Inference | None) -> TriageResult:
    """Decide the route.

    `inference` is None (or has quality_pass False) only when the server
    quality check has failed on the retake as well; the API asks for one
    retake before calling triage with a failed result.
    """
    fired: list[str] = []
    route: str | None = None

    def hit(code: str, r: str) -> None:
        nonlocal route
        fired.append(code)
        if route is None:
            route = r

    # Rules 1 and 2: intake red flags (urgent first, then dermatologist).
    for flag in sorted(intake.red_flags_true, key=lambda f: (_ROUTE_PRIORITY[f.route], f.code)):
        hit(f"redflag:{flag.code}", flag.route)

    if inference is None or not inference.quality_pass:
        # Rule 4 (quality branch).
        hit("quality:failed", "dermatologist")
    else:
        # Rule 3: model refer-out head.
        if inference.refer_out_probability >= inference.thresholds.get("refer_out", 0.30):
            hit("model:refer_out", "dermatologist")
        # Rule 4: unfamiliar image.
        if inference.ood_flag:
            hit("model:ood", "dermatologist")

        labels = inference.labels
        # Rule 5: severity.
        acne = labels.get("acne")
        if acne is not None and (
            acne.grade == "marked" or (acne.grade == "moderate" and intake.duration_weeks("acne") > 12)
        ):
            hit("severity:acne", "dermatologist")
        for code in ("hyperpigmentation", "erythema", "texture"):
            lab = labels.get(code)
            if lab is not None and lab.grade == "marked":
                hit(f"severity:{code}", "iconic_clinic")

        # Rule 6: moderate cosmetic or several concerns.
        present = [c for c, lab in labels.items() if lab.present]
        if any(lab.grade == "moderate" for lab in labels.values()) or len(present) >= 2:
            hit("cosmetic:moderate_or_multiple", "iconic_clinic")

        # Informational only: does not change the route.
        if any(lab.uncertain for lab in labels.values()):
            fired.append("model:uncertain_label")

    # Rule 7: nothing fired.
    final = route or "self_care"
    if route is None:
        fired.append("cosmetic:mild_or_none")
    return TriageResult(
        route=final,
        reasons=tuple(fired),
        allow_actives=final in ("iconic_clinic", "self_care"),
        rule_set_version=RULE_SET_VERSION,
    )
