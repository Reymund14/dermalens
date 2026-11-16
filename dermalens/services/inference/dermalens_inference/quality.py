"""Server-side image quality re-check.

Mirrors the on-device capture gate. The app checks face landmarks and head
pose live; the server cannot run the landmark model cheaply, so it uses a skin
pixel mask (YCbCr range) to confirm a face-sized skin region instead, and
repeats the sharpness, exposure and even-lighting checks exactly.
"""
from __future__ import annotations

import io
from dataclasses import asdict, dataclass

import numpy as np
from PIL import Image, ImageOps

# Pass rules from the roadmap ("tune in pilot").
MIN_SHARPNESS = 100.0
EXPOSURE_RANGE = (110.0, 190.0)
MAX_CLIPPED = 0.02
MAX_LR_DIFF = 0.15
MIN_SKIN_COVERAGE = 0.15
MIN_SIDE_PX = 480


@dataclass
class QualityReport:
    width_px: int
    height_px: int
    blur_score: float
    brightness_mean: float
    clipped_fraction: float
    lr_balance_diff: float | None
    face_coverage: float
    checks: dict[str, bool]
    quality_pass: bool

    def to_dict(self) -> dict:
        return asdict(self)


def load_image(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)  # respect orientation, then drop EXIF entirely
    return img.convert("RGB")


def strip_exif(data: bytes) -> bytes:
    """Re-encode as JPEG without any metadata (GPS, device serials)."""
    img = load_image(data)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=92)
    return out.getvalue()


def skin_mask(rgb: np.ndarray) -> np.ndarray:
    """Classic YCbCr skin range; robust across Fitzpatrick I-VI for a coarse mask."""
    r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
    return (cb >= 77) & (cb <= 127) & (cr >= 133) & (cr <= 173) & (y > 30)


def laplacian_variance(gray: np.ndarray) -> float:
    g = gray.astype(np.float32)
    lap = (-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:])
    return float(lap.var())


def check(data: bytes, view: str = "front") -> QualityReport:
    img = load_image(data)
    w, h = img.size
    # Work at a fixed scale so thresholds do not depend on the phone's resolution.
    scale = 720 / max(w, h)
    small = img.resize((max(1, int(w * scale)), max(1, int(h * scale)))) if scale < 1 else img
    rgb = np.asarray(small)
    lab_l = np.asarray(small.convert("LAB"))[..., 0].astype(np.float32)
    mask = skin_mask(rgb)
    coverage = float(mask.mean())

    sk = lab_l[mask] if mask.sum() > 100 else lab_l.ravel()
    brightness = float(sk.mean())
    clipped = float(((sk >= 250) | (sk <= 5)).mean())

    gray = np.asarray(small.convert("L"))
    hh, ww = gray.shape
    centre = gray[hh // 4: 3 * hh // 4, ww // 4: 3 * ww // 4]
    sharp = laplacian_variance(centre)

    lr = None
    if view == "front":
        left = lab_l[:, : ww // 2][mask[:, : ww // 2]]
        right = lab_l[:, ww // 2:][mask[:, ww // 2:]]
        if left.size > 50 and right.size > 50:
            a, b = float(left.mean()), float(right.mean())
            lr = abs(a - b) / max(a, b, 1.0)

    checks = {
        "resolution": min(w, h) >= MIN_SIDE_PX,
        "face_present": coverage >= MIN_SKIN_COVERAGE,
        "sharpness": sharp >= MIN_SHARPNESS,
        "exposure": EXPOSURE_RANGE[0] <= brightness <= EXPOSURE_RANGE[1] and clipped < MAX_CLIPPED,
        "even_lighting": lr is None or lr <= MAX_LR_DIFF,
    }
    return QualityReport(
        width_px=w, height_px=h, blur_score=round(sharp, 2), brightness_mean=round(brightness, 2),
        clipped_fraction=round(clipped, 4), lr_balance_diff=None if lr is None else round(lr, 4),
        face_coverage=round(coverage, 4), checks=checks, quality_pass=all(checks.values()),
    )
