"""Multi-label classifier wrappers.

Two implementations share one post-processing path (calibration, thresholds,
uncertainty band, grades, OOD flag) so swapping the stub for the trained model
changes nothing downstream:

* `StubClassifier` -- deterministic image-statistics heuristic. It exists so the
  app, triage and recommendation engine can be built and demoed while the real
  model trains (roadmap build step 6). It is NOT a trained model and must not
  be used with real patients.
* `OnnxClassifier` -- loads the exported ConvNeXt/EfficientNet model (ONNX,
  opset 17) and verifies its SHA-256 against the registered model version.

The model only scores images. It never decides routes; that is the rules
package's job.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from .quality import load_image, skin_mask

LABELS = ("acne", "hyperpigmentation", "erythema", "texture")
VIEWS = ("front", "left45", "right45")
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
INPUT_SIZE = 384


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


@dataclass
class ModelConfig:
    model_version_id: str
    architecture: str
    thresholds: dict[str, float]          # per label + "refer_out"
    temperature: dict[str, float]         # per label + "refer_out"
    ood_threshold: float
    uncertainty_band: float = 0.10
    extra: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "ModelConfig":
        d = json.loads(Path(path).read_text())
        return cls(**d)


STUB_CONFIG = ModelConfig(
    model_version_id="dl-stub-0.1.0",
    architecture="heuristic-stub (not a trained model)",
    thresholds={"acne": 0.5, "hyperpigmentation": 0.5, "erythema": 0.5, "texture": 0.5, "refer_out": 0.30},
    temperature={"acne": 1.0, "hyperpigmentation": 1.0, "erythema": 1.0, "texture": 1.0, "refer_out": 1.0},
    ood_threshold=0.5,
)


@dataclass
class RawOutput:
    presence_logits: dict[str, float]
    grade_logits: dict[str, tuple[float, float]]  # CORAL: P(>mild), P(>moderate)
    refer_out_logit: float
    ood_score: float


def postprocess(raw: RawOutput, cfg: ModelConfig, quality_pass: bool) -> dict:
    """Turn raw logits into the inference contract."""
    labels = {}
    for code in LABELS:
        t = cfg.temperature.get(code, 1.0)
        p = sigmoid(raw.presence_logits[code] / t)
        thr = cfg.thresholds[code]
        present = p >= thr
        uncertain = abs(p - thr) <= cfg.uncertainty_band
        grade = "none"
        if present:
            k1, k2 = raw.grade_logits[code]
            steps = int(sigmoid(k1) >= 0.5) + int(sigmoid(k1) >= 0.5 and sigmoid(k2) >= 0.5)
            grade = ("mild", "moderate", "marked")[steps]
        labels[code] = {"p": round(p, 4), "present": present, "grade": grade, "uncertain": uncertain}
    refer = sigmoid(raw.refer_out_logit / cfg.temperature.get("refer_out", 1.0))
    return {
        "model_version_id": cfg.model_version_id,
        "quality_pass": quality_pass,
        "ood_score": round(raw.ood_score, 4),
        "ood_flag": raw.ood_score >= cfg.ood_threshold,
        "refer_out_probability": round(refer, 4),
        "thresholds": {"refer_out": cfg.thresholds["refer_out"]},
        "labels": labels,
    }


# ----- Preprocessing (shared) -------------------------------------------------

def crop_to_skin(img: Image.Image, margin: float = 0.10) -> Image.Image:
    """Crop to the skin-region bounding box plus a margin (face-box stand-in)."""
    rgb = np.asarray(img)
    m = skin_mask(rgb)
    if m.sum() < 100:
        return img
    ys, xs = np.where(m)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    dy, dx = int((y1 - y0) * margin), int((x1 - x0) * margin)
    h, w = m.shape
    return img.crop((max(0, x0 - dx), max(0, y0 - dy), min(w, x1 + dx), min(h, y1 + dy)))


def gray_world(arr: np.ndarray) -> np.ndarray:
    """Gray-world colour constancy on a float RGB array in [0, 1]."""
    means = arr.reshape(-1, 3).mean(axis=0) + 1e-6
    return np.clip(arr * (means.mean() / means), 0.0, 1.0)


def preprocess(img: Image.Image) -> np.ndarray:
    face = crop_to_skin(img).resize((INPUT_SIZE, INPUT_SIZE), Image.BILINEAR)
    arr = np.asarray(face).astype(np.float32) / 255.0
    arr = gray_world(arr)
    arr = (arr - IMAGENET_MEAN) / IMAGENET_STD
    return arr.transpose(2, 0, 1)  # CHW


# ----- Stub -------------------------------------------------------------------

class StubClassifier:
    """Deterministic heuristic from skin-pixel statistics. NOT a trained model."""

    def __init__(self, cfg: ModelConfig = STUB_CONFIG):
        self.cfg = cfg

    @staticmethod
    def _features(img: Image.Image) -> dict[str, float]:
        small = crop_to_skin(img).resize((256, 256))
        rgb = np.asarray(small)
        lab = np.asarray(small.convert("LAB")).astype(np.float32)
        m = skin_mask(rgb)
        coverage = float(m.mean())
        if m.sum() < 200:
            return {"coverage": coverage, "redness": 0.0, "unevenness": 0.0, "texture": 0.0, "spots": 0.0}
        L, A = lab[..., 0], lab[..., 1]
        redness = float(A[m].mean() - 128.0)            # a* above neutral
        unevenness = float(L[m].std())                  # tone variation
        g = L
        hf = np.abs(g[1:-1, 1:-1] * 4 - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:])
        texture = float(hf[m[1:-1, 1:-1]].mean())
        a_thr = np.percentile(A[m], 97)
        spots = float(((A > a_thr + 4) & m).mean() * 100)  # % of very red pixels
        return {"coverage": coverage, "redness": redness, "unevenness": unevenness, "texture": texture,
                "spots": spots}

    def raw(self, images: dict[str, bytes]) -> RawOutput:
        feats = [self._features(load_image(images[v])) for v in VIEWS if v in images]
        f = {k: float(np.mean([x[k] for x in feats])) for k in feats[0]}
        pres = {
            "erythema": (f["redness"] - 22.0) / 3.0,
            "hyperpigmentation": (f["unevenness"] - 14.0) / 2.5,
            "texture": (f["texture"] - 9.0) / 2.0,
            "acne": (f["spots"] - 1.2) / 0.4,
        }
        grades = {k: (v - 1.0, v - 3.0) for k, v in pres.items()}
        ood = 1.0 - min(1.0, f["coverage"] / 0.25)
        return RawOutput(presence_logits=pres, grade_logits=grades, refer_out_logit=-4.0, ood_score=ood)

    def predict(self, images: dict[str, bytes], quality_pass: bool) -> dict:
        return postprocess(self.raw(images), self.cfg, quality_pass)


# ----- ONNX -------------------------------------------------------------------

class OnnxClassifier:
    """Trained model served with ONNX Runtime.

    Expected graph: input "images" float32 [V, 3, 384, 384] (one row per view);
    outputs "presence" [4], "grades" [4, 2] (CORAL logits), "refer_out" [1] and
    optionally "embedding" [D]. With an embedding and `extra.ood_stats` (mean,
    inverse covariance as JSON lists) the OOD score is a squashed Mahalanobis
    distance; otherwise it falls back to an energy score on the presence logits.
    """

    def __init__(self, model_path: str | Path, cfg: ModelConfig, expected_sha256: str | None = None):
        import onnxruntime as ort

        data = Path(model_path).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if expected_sha256 and digest != expected_sha256:
            raise RuntimeError(f"model checksum mismatch: {digest} != {expected_sha256}")
        self.sha256 = digest
        self.cfg = cfg
        self.session = ort.InferenceSession(data, providers=["CPUExecutionProvider"])
        stats = cfg.extra.get("ood_stats")
        self._ood_mean = np.array(stats["mean"], dtype=np.float32) if stats else None
        self._ood_icov = np.array(stats["inv_cov"], dtype=np.float32) if stats else None
        self._ood_scale = float(stats.get("scale", 1.0)) if stats else 1.0

    def raw(self, images: dict[str, bytes]) -> RawOutput:
        batch = np.stack([preprocess(load_image(images[v])) for v in VIEWS if v in images]).astype(np.float32)
        names = [o.name for o in self.session.get_outputs()]
        outs = dict(zip(names, self.session.run(None, {"images": batch})))
        pres = np.asarray(outs["presence"], dtype=np.float32).reshape(-1)
        grades = np.asarray(outs["grades"], dtype=np.float32).reshape(4, 2)
        refer = float(np.asarray(outs["refer_out"]).reshape(-1)[0])
        if "embedding" in outs and self._ood_mean is not None:
            e = np.asarray(outs["embedding"], dtype=np.float32).reshape(-1) - self._ood_mean
            d = float(np.sqrt(max(0.0, e @ self._ood_icov @ e)))
            ood = 1.0 - math.exp(-d / self._ood_scale)
        else:
            energy = -float(np.mean(np.logaddexp(0, np.abs(pres))))  # low confidence -> high energy
            ood = sigmoid(energy + 2.0)
        return RawOutput(
            presence_logits={c: float(pres[i]) for i, c in enumerate(LABELS)},
            grade_logits={c: (float(grades[i, 0]), float(grades[i, 1])) for i, c in enumerate(LABELS)},
            refer_out_logit=refer,
            ood_score=ood,
        )

    def predict(self, images: dict[str, bytes], quality_pass: bool) -> dict:
        return postprocess(self.raw(images), self.cfg, quality_pass)
