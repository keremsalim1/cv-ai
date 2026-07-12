import time
import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def make_token(sub: str = "user-1", aud: str = "authenticated", exp_delta: int = 3600) -> str:
    payload = {"sub": sub, "aud": aud, "exp": int(time.time()) + exp_delta}
    return jwt.encode(payload, get_settings().supabase_jwt_secret, algorithm="HS256")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict:
    return {"Authorization": f"Bearer {make_token()}"}
