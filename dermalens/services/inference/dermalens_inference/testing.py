"""Synthetic test images (no real faces in the repo)."""
import io

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def synth_face(seed=0, red_spots=0, brightness=1.0, blur=0.0, size=(900, 1200), tone=(205, 150, 120)):
    """A skin-toned oval on a neutral background with fine texture noise."""
    rng = np.random.default_rng(seed)
    w, h = size
    img = Image.new("RGB", size, (60, 70, 80))
    d = ImageDraw.Draw(img)
    d.ellipse((w * 0.18, h * 0.12, w * 0.82, h * 0.88), fill=tone)
    for _ in range(red_spots):
        x, y = rng.integers(int(w * 0.3), int(w * 0.7)), rng.integers(int(h * 0.3), int(h * 0.7))
        d.ellipse((x - 6, y - 6, x + 6, y + 6), fill=(200, 70, 70))
    arr = np.asarray(img).astype(np.float32)
    arr += rng.normal(0, 10, arr.shape)
    arr = np.clip(arr * brightness, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()
