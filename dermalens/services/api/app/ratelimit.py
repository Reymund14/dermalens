"""Small in-process rate limiter for the auth endpoints (argon2 is expensive).

shortcut: per-process memory only, so run one API instance or move to Redis
when the API scales horizontally.
"""
from __future__ import annotations

import threading
import time

from fastapi import HTTPException

from .config import settings

_hits: dict[str, list[float]] = {}
_lock = threading.Lock()


def enforce(key: str, limit: int, window_seconds: int) -> None:
    if not settings.auth_rate_limit_enabled:
        return
    now = time.monotonic()
    with _lock:
        if len(_hits) > 4096:  # drop keys that fell out of their window
            for k in [k for k, v in _hits.items() if not v or v[-1] <= now - window_seconds]:
                _hits.pop(k, None)
        hits = [t for t in _hits.get(key, []) if t > now - window_seconds]
        if len(hits) >= limit:
            _hits[key] = hits
            raise HTTPException(429, "too many attempts; try again later")
        hits.append(now)
        _hits[key] = hits


def reset() -> None:
    """Tests only."""
    with _lock:
        _hits.clear()
