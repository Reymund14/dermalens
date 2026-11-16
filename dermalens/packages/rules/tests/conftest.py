import pytest

from dermalens_rules import Inference, LabelResult


def make_inference(grades=None, refer_out=0.02, ood=False, quality=True, uncertain=()):
    grades = grades or {}
    labels = {}
    for code in ("acne", "hyperpigmentation", "erythema", "texture"):
        g = grades.get(code, "none")
        present = g != "none"
        labels[code] = LabelResult(p=0.8 if present else 0.1, present=present, grade=g, uncertain=code in uncertain)
    return Inference(model_version_id="test", quality_pass=quality, ood_score=0.9 if ood else 0.1, ood_flag=ood,
                     refer_out_probability=refer_out, labels=labels)


@pytest.fixture
def inf():
    return make_inference
