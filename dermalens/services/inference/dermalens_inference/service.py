"""Inference entry point used both by the HTTP service and in-process by the API."""
from __future__ import annotations

import os
import time
from functools import lru_cache

from .classifier import STUB_CONFIG, ModelConfig, OnnxClassifier, StubClassifier
from .quality import check


@lru_cache(maxsize=1)
def get_classifier():
    path = os.getenv("DERMALENS_MODEL_PATH")
    if path:
        cfg = ModelConfig.load(os.environ["DERMALENS_MODEL_CONFIG"])
        return OnnxClassifier(path, cfg, expected_sha256=os.getenv("DERMALENS_MODEL_SHA256"))
    return StubClassifier(STUB_CONFIG)


def infer(images: dict[str, bytes]) -> dict:
    """Run quality re-check + classifier on the three standard views."""
    t0 = time.perf_counter()
    quality = {view: check(data, view).to_dict() for view, data in images.items()}
    required = ("front", "left45", "right45")
    quality_pass = all(v in quality and quality[v]["quality_pass"] for v in required)
    clf = get_classifier()
    result = clf.predict({v: images[v] for v in required if v in images}, quality_pass)
    result["quality"] = quality
    result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
    return result
