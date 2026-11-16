"""Inference service HTTP API (internal only; put it behind mTLS in production)."""
from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, UploadFile

from .quality import check
from .service import get_classifier, infer

app = FastAPI(title="DermaLens inference", version="0.1.0")


@app.get("/health")
def health():
    clf = get_classifier()
    return {"ok": True, "model_version_id": clf.cfg.model_version_id, "architecture": clf.cfg.architecture}


@app.post("/infer")
async def infer_endpoint(front: UploadFile = File(...), left45: UploadFile = File(...),
                         right45: UploadFile = File(...)):
    images = {"front": await front.read(), "left45": await left45.read(), "right45": await right45.read()}
    if not all(images.values()):
        raise HTTPException(422, "all three views are required")
    return infer(images)


@app.post("/quality")
async def quality_endpoint(view: str, image: UploadFile = File(...)):
    return check(await image.read(), view).to_dict()
