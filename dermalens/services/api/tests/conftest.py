import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "packages/rules"), str(ROOT / "services/inference"), str(ROOT / "services/api")]

_tmp = tempfile.mkdtemp(prefix="dermalens-test-")
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["STORAGE_DIR"] = f"{_tmp}/storage"
os.environ["AUTH_RATE_LIMIT_ENABLED"] = "0"  # one shared test client IP
os.environ["RATE_LIMITS"] = "0"  # account/notification endpoints share that IP too
os.environ["JWT_SECRET"] = os.getenv("JWT_SECRET", "test-jwt-secret")
os.environ["DATA_KEY"] = os.getenv("DATA_KEY", "fTA4PmOBPQOqUonU7by3kz0w16L633fEB9-4R1rQfuI=")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402

from dermalens_inference.testing import synth_face  # noqa: E402,F401


@pytest.fixture(scope="session", autouse=True)
def _db():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db, dev_accounts=True)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
