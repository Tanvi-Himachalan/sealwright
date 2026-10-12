"""Test setup.

Environment variables are set BEFORE the app is imported so that the tests use
a throw-away SQLite file + temp folder, and process jobs inline (synchronously)
so results are deterministic and no sleeping/polling is needed.
"""
import os
import shutil
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="sealwright_tests_"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["STORAGE_DIR"] = str(_TMP / "certs")
os.environ["PROCESS_INLINE"] = "true"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["PUBLIC_BASE_URL"] = "http://testserver"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_state():
    """Fresh tables and an empty certificate folder for every test."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    shutil.rmtree(settings.storage_dir, ignore_errors=True)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def job_payload():
    return {
        "title": "Python Bootcamp 2026",
        "issuer": "Frontier Academy",
        "signatory_name": "Dr. A. Rao",
        "signatory_title": "Program Director",
        "recipients": [
            {"name": "Tanvi Sharma", "email": "tanvi@example.com"},
            {"name": "Arjun Mehta", "email": "arjun@example.com", "remark": "with Distinction"},
            {"name": "Meera Iyer"},
        ],
    }


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)
