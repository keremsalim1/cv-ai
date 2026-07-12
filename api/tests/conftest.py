import time
from types import SimpleNamespace

import jwt
import pytest
from fastapi.testclient import TestClient
from fpdf import FPDF

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


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    pdf.multi_cell(0, 10,
        "Ada Lovelace\nSoftware Engineer\nada@example.com\n"
        "Skills: Python, SQL, FastAPI\n"
        "Experience: Analytical Engine Corp, Developer, 2020-2024")
    return bytes(pdf.output())


@pytest.fixture(autouse=True)
def _reset_usage():
    from app.services.usage import usage_store
    usage_store._counts.clear()
    yield


class FakeOpenAI:
    """Mimics openai.OpenAI: returns queued message contents in order."""

    def __init__(self, contents: list[str]):
        self._contents = list(contents)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        content = self._contents.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )
