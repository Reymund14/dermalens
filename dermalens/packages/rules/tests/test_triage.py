import pytest

from dermalens_rules import Intake, RedFlag, ReportedConcern, triage

from .conftest import make_inference

URGENT = RedFlag("rapid_swelling", "urgent_care")
DERM = RedFlag("changing_mole", "dermatologist")

CASES = [
    # (name, intake, inference, expected route, expected first reason)
    ("nothing detected", Intake(), make_inference(), "self_care", "cosmetic:mild_or_none"),
    ("one mild label", Intake(), make_inference({"acne": "mild"}), "self_care", "cosmetic:mild_or_none"),
    ("urgent flag wins over everything", Intake(red_flags_true=(DERM, URGENT)), make_inference({"acne": "marked"}),
     "urgent_care", "redflag:rapid_swelling"),
    ("derm flag", Intake(red_flags_true=(DERM,)), make_inference(), "dermatologist", "redflag:changing_mole"),
    ("model refer-out", Intake(), make_inference(refer_out=0.5), "dermatologist", "model:refer_out"),
    ("refer-out at threshold fires", Intake(), make_inference(refer_out=0.30), "dermatologist", "model:refer_out"),
    ("refer-out below threshold", Intake(), make_inference(refer_out=0.29), "self_care", "cosmetic:mild_or_none"),
    ("ood", Intake(), make_inference(ood=True), "dermatologist", "model:ood"),
    ("quality failed twice", Intake(), make_inference(quality=False), "dermatologist", "quality:failed"),
    ("no inference", Intake(), None, "dermatologist", "quality:failed"),
    ("marked acne", Intake(), make_inference({"acne": "marked"}), "dermatologist", "severity:acne"),
    ("moderate acne > 12 weeks", Intake(concerns=(ReportedConcern("acne", 2, 13),)),
     make_inference({"acne": "moderate"}), "dermatologist", "severity:acne"),
    ("moderate acne exactly 12 weeks", Intake(concerns=(ReportedConcern("acne", 2, 12),)),
     make_inference({"acne": "moderate"}), "iconic_clinic", "cosmetic:moderate_or_multiple"),
    ("marked pigment", Intake(), make_inference({"hyperpigmentation": "marked"}), "iconic_clinic",
     "severity:hyperpigmentation"),
    ("marked redness", Intake(), make_inference({"erythema": "marked"}), "iconic_clinic", "severity:erythema"),
    ("marked texture", Intake(), make_inference({"texture": "marked"}), "iconic_clinic", "severity:texture"),
    ("two mild labels", Intake(), make_inference({"acne": "mild", "texture": "mild"}), "iconic_clinic",
     "cosmetic:moderate_or_multiple"),
    ("one moderate", Intake(), make_inference({"erythema": "moderate"}), "iconic_clinic",
     "cosmetic:moderate_or_multiple"),
]


@pytest.mark.parametrize("name,intake,inference,route,first", CASES, ids=[c[0] for c in CASES])
def test_cascade(name, intake, inference, route, first):
    r = triage(intake, inference)
    assert r.route == route
    assert r.reasons[0] == first
    assert r.allow_actives == (route in ("iconic_clinic", "self_care"))


def test_red_flag_beats_confident_model():
    r = triage(Intake(red_flags_true=(DERM,)), make_inference(refer_out=0.0))
    assert r.route == "dermatologist"


def test_every_fired_rule_recorded():
    r = triage(Intake(red_flags_true=(DERM,)), make_inference({"acne": "marked"}, refer_out=0.9, ood=True))
    assert r.reasons[:4] == ("redflag:changing_mole", "model:refer_out", "model:ood", "severity:acne")


def test_uncertain_is_informational():
    r = triage(Intake(), make_inference({"acne": "mild"}, uncertain=("erythema",)))
    assert r.route == "self_care"
    assert "model:uncertain_label" in r.reasons


def test_deterministic():
    i, m = Intake(red_flags_true=(DERM,)), make_inference({"texture": "moderate"})
    assert triage(i, m) == triage(i, m)
