import io
import json

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from dermalens_inference.classifier import (
    LABELS, STUB_CONFIG, ModelConfig, OnnxClassifier, RawOutput, StubClassifier, postprocess,
)
from dermalens_inference.quality import check, strip_exif
from dermalens_inference.service import infer
from dermalens_inference.testing import synth_face


def test_quality_pass_on_good_image():
    r = check(synth_face(), "front")
    assert r.quality_pass, r.checks


def test_quality_pass_on_phone_resized_image():
    im = Image.open(io.BytesIO(synth_face(size=(3024, 4032))))
    im.thumbnail((1440, 1440))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90)
    r = check(strip_exif(buf.getvalue()), "front")
    assert r.quality_pass, r.checks


def test_quality_fails_when_blurred():
    r = check(synth_face(blur=6), "front")
    assert not r.checks["sharpness"]


def test_quality_fails_when_dark():
    r = check(synth_face(brightness=0.35), "front")
    assert not r.checks["exposure"]


def test_quality_fails_without_face():
    buf = io.BytesIO()
    Image.new("RGB", (900, 1200), (40, 90, 160)).save(buf, format="JPEG")
    assert not check(buf.getvalue(), "front").checks["face_present"]


def test_strip_exif_removes_metadata():
    img = Image.open(io.BytesIO(synth_face()))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    out = Image.open(io.BytesIO(strip_exif(buf.getvalue())))
    assert len(out.getexif()) == 0


def test_contract_shape_and_determinism():
    imgs = {"front": synth_face(1), "left45": synth_face(2), "right45": synth_face(3)}
    a, b = infer(imgs), infer(imgs)
    for k in ("model_version_id", "quality_pass", "ood_score", "ood_flag", "refer_out_probability", "labels"):
        assert k in a
    assert set(a["labels"]) == set(LABELS)
    a.pop("latency_ms"), b.pop("latency_ms")
    assert a == b


def test_stub_sees_red_spots_more_than_clean_skin():
    clf = StubClassifier()
    clean = clf.raw({"front": synth_face(5)}).presence_logits["acne"]
    spotty = clf.raw({"front": synth_face(5, red_spots=40)}).presence_logits["acne"]
    assert spotty > clean


def test_postprocess_uncertainty_and_grades():
    raw = RawOutput(
        presence_logits={"acne": 3.0, "hyperpigmentation": 0.1, "erythema": -3.0, "texture": 2.0},
        grade_logits={"acne": (2.0, 2.0), "hyperpigmentation": (0, 0), "erythema": (0, 0), "texture": (2.0, -2.0)},
        refer_out_logit=-3.0, ood_score=0.1)
    out = postprocess(raw, STUB_CONFIG, True)
    assert out["labels"]["acne"]["grade"] == "marked"
    assert out["labels"]["texture"]["grade"] == "moderate"
    assert out["labels"]["erythema"]["present"] is False
    assert out["labels"]["hyperpigmentation"]["uncertain"] is True


def _tiny_onnx(path):
    onnx = pytest.importorskip("onnx")
    from onnx import TensorProto, helper

    inp = helper.make_tensor_value_info("images", TensorProto.FLOAT, [None, 3, 384, 384])
    pooled = helper.make_node("ReduceMean", ["images"], ["m"], keepdims=0)  # [] scalar-ish mean
    nodes = [pooled]
    outs = []
    for name, shape, vals in [("presence", [4], [2.0, -2.0, 0.0, 1.5]),
                              ("grades", [4, 2], [1.0, -1.0] * 4),
                              ("refer_out", [1], [-5.0])]:
        nodes.append(helper.make_node("Constant", [], [name + "_c"],
                                      value=helper.make_tensor(name + "_v", TensorProto.FLOAT, shape, vals)))
        nodes.append(helper.make_node("Identity", [name + "_c"], [name]))
        outs.append(helper.make_tensor_value_info(name, TensorProto.FLOAT, shape))
    outs.append(helper.make_tensor_value_info("m", TensorProto.FLOAT, None))
    graph = helper.make_graph(nodes, "tiny", [inp], outs)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    onnx.save(model, path)


def test_onnx_classifier_end_to_end(tmp_path):
    pytest.importorskip("onnxruntime")
    p = tmp_path / "m.onnx"
    _tiny_onnx(str(p))
    cfg = ModelConfig(model_version_id="dl-test", architecture="tiny", thresholds=dict(STUB_CONFIG.thresholds),
                      temperature=dict(STUB_CONFIG.temperature), ood_threshold=0.9)
    clf = OnnxClassifier(p, cfg)
    out = clf.predict({"front": synth_face(), "left45": synth_face(1), "right45": synth_face(2)}, True)
    assert out["model_version_id"] == "dl-test"
    assert out["labels"]["acne"]["present"] and out["labels"]["acne"]["grade"] == "moderate"
    assert not out["labels"]["hyperpigmentation"]["present"]
    with pytest.raises(RuntimeError):
        OnnxClassifier(p, cfg, expected_sha256="0" * 64)
    json.dumps(out)
