import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql://cowsay:cowsay@localhost:5432/cowsay")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.main import app  # noqa: E402  (import after env vars are set)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
