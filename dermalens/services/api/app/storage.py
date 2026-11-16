"""Object storage. Local disk in development; swap for S3-compatible storage
(server-side encryption, private bucket, 5-minute pre-signed URLs) in production
by implementing the same three functions."""
from __future__ import annotations

import shutil
from pathlib import Path

from .config import settings


def _path(key: str) -> Path:
    p = (settings.storage_dir / key).resolve()
    root = settings.storage_dir.resolve()
    if root not in p.parents:
        raise ValueError("invalid object key")
    return p


def put(key: str, data: bytes) -> None:
    p = _path(key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def get(key: str) -> bytes:
    return _path(key).read_bytes()


def delete_prefix(prefix: str) -> None:
    p = _path(prefix)
    if p.exists():
        shutil.rmtree(p) if p.is_dir() else p.unlink()
