"""Small in-process rate limiter for the auth endpoints (argon2 is expensive).

shortcut: per-process memory only, so run one API instance or move to Redis
when the API scales horizontally.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from .config import settings

_hits: dict[str, list[float]] = {}
_recent: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def hit(key: str, limit: int, window_s: int) -> None:
    """Sliding-window limit for the account/notification endpoints."""
    if not settings.rate_limits:
        return
    now = time.monotonic()
    with _lock:
        q = _recent[key]
        while q and q[0] <= now - window_s:
            q.popleft()
        if len(q) >= limit:
            retry = int(q[0] + window_s - now) + 1
            raise HTTPException(429, "too many attempts; please wait and try again",
                                headers={"Retry-After": str(retry)})
        q.append(now)


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
        _recent.clear()
