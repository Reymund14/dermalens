from fastapi import HTTPException
import pytest

from app import ratelimit
from app.config import settings


def test_enforce_blocks_after_limit(monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit_enabled", True)
    ratelimit.reset()
    for _ in range(3):
        ratelimit.enforce("test-key", limit=3, window_seconds=60)
    with pytest.raises(HTTPException) as err:
        ratelimit.enforce("test-key", limit=3, window_seconds=60)
    assert err.value.status_code == 429
