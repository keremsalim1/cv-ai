# CV-AI API Backend (Plan 1/2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FastAPI backend that parses CV PDFs, analyzes job postings, scores CV-job fit (1-5 stars), and generates ATS-compliant PDFs — fully testable with mocked OpenAI.

**Architecture:** Stateless FastAPI service. Endpoints verify Supabase JWTs, enforce a daily AI-usage limit, and delegate to service modules (PDF extract → LLM parse → score/rewrite → PDF render). All LLM calls go through one `LLMClient` wrapper with JSON validation + one retry. Persistence (DB/Storage) belongs to Plan 2 (frontend + Supabase).

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, PyMuPDF (extract), fpdf2 (render — replaces spec's WeasyPrint: no GTK dependency, works on Windows), trafilatura+httpx (job fetch), OpenAI SDK v1, PyJWT, pytest.

## Global Constraints

- Python 3.11; all commands run from `api/` with venv activated (`.venv\Scripts\activate` on Windows PowerShell).
- Models: `MODEL_FAST = "gpt-4o-mini"` (CV parse, job criteria), `MODEL_SMART = "gpt-4o"` (scoring, ATS rewrite).
- Upload limit: 10 MB, PDF only. Extracted text < 50 chars ⇒ treated as scanned PDF (error code `SCANNED_PDF`).
- Daily AI limit per user: `DAILY_AI_LIMIT = 20` ⇒ HTTP 429 with code `DAILY_LIMIT_REACHED`.
- Stars mapping (server-side, never trusted from LLM): 0-20→1★, 21-40→2★, 41-60→3★, 61-80→4★, 81-100→5★.
- Scoring rubric weights (fixed in prompt): skills 40%, experience 35%, education/other 25%.
- Auth: Supabase JWT, HS256, audience `authenticated`; user id = `sub` claim. Missing/invalid ⇒ 401.
- Tests NEVER call real OpenAI or real websites — always fakes/monkeypatch.
- TDD: every task = failing test → minimal code → pass → commit. Repo root: `C:\Users\ASUS\Desktop\cv-ai`.

---

### Task 1: Project scaffold + health endpoint

**Files:**
- Create: `api/requirements.txt`, `api/pyproject.toml`, `api/app/__init__.py`, `api/app/main.py`, `api/tests/__init__.py`, `api/tests/test_health.py`, `.gitignore` (repo root)

**Interfaces:**
- Produces: FastAPI instance `app.main.app`; test command `python -m pytest`.

- [ ] **Step 1: Create structure, venv, install dependencies**

```powershell
cd C:\Users\ASUS\Desktop\cv-ai
mkdir api\app, api\tests
python -m venv api\.venv
api\.venv\Scripts\pip install fastapi "uvicorn[standard]" "pydantic>=2" pydantic-settings python-multipart pymupdf trafilatura "openai>=1" pyjwt fpdf2 httpx pytest
api\.venv\Scripts\pip freeze > api\requirements.txt
```

`.gitignore` (repo root):
```
.venv/
__pycache__/
*.pyc
.env
.pytest_cache/
node_modules/
.next/
```

`api/pyproject.toml`:
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

Create empty `api/app/__init__.py` and `api/tests/__init__.py`.

- [ ] **Step 2: Write the failing test**

`api/tests/test_health.py`:
```python
from fastapi.testclient import TestClient
from app.main import app

def test_health():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 3: Run test to verify it fails**

Run (from `api/`): `.venv\Scripts\python -m pytest -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 4: Write minimal implementation**

`api/app/main.py`:
```python
from fastapi import FastAPI

app = FastAPI(title="CV-AI API")

@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest -v`
Expected: `1 passed`

- [ ] **Step 6: Commit**

```powershell
git add .gitignore api
git commit -m "feat(api): scaffold FastAPI app with health endpoint"
```

---

### Task 2: Settings + Supabase JWT auth dependency

**Files:**
- Create: `api/app/config.py`, `api/app/auth.py`, `api/.env.example`, `api/tests/conftest.py`, `api/tests/test_auth.py`

**Interfaces:**
- Produces: `get_settings() -> Settings` (fields: `openai_api_key: str`, `supabase_jwt_secret: str`, `daily_ai_limit: int`); `get_current_user(...) -> str` FastAPI dependency returning user id; test fixture `auth_headers: dict`.

- [ ] **Step 1: Write the failing test**

`api/tests/conftest.py`:
```python
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
```

`api/tests/test_auth.py`:
```python
from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.main import app
from tests.conftest import make_token

router = APIRouter()

@router.get("/whoami")
def whoami(user_id: str = Depends(get_current_user)):
    return {"user_id": user_id}

app.include_router(router)


def test_valid_token(client, auth_headers):
    r = client.get("/whoami", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"user_id": "user-1"}

def test_missing_token(client):
    assert client.get("/whoami").status_code == 401

def test_bad_signature(client):
    import jwt, time
    bad = jwt.encode({"sub": "x", "aud": "authenticated", "exp": int(time.time()) + 60},
                     "wrong-secret", algorithm="HS256")
    assert client.get("/whoami", headers={"Authorization": f"Bearer {bad}"}).status_code == 401

def test_wrong_audience(client):
    tok = make_token(aud="anon")
    assert client.get("/whoami", headers={"Authorization": f"Bearer {tok}"}).status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 3: Write minimal implementation**

`api/app/config.py`:
```python
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = ""
    supabase_jwt_secret: str = "test-secret-change-in-prod"
    daily_ai_limit: int = 20

    model_config = {"env_file": ".env"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`api/app/auth.py`:
```python
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    if creds is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(
            creds.credentials,
            get_settings().supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload["sub"]
```

`api/.env.example`:
```
OPENAI_API_KEY=sk-...
SUPABASE_JWT_SECRET=your-supabase-jwt-secret
DAILY_AI_LIMIT=20
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```powershell
git add api
git commit -m "feat(api): settings + Supabase JWT auth dependency"
```

---

### Task 3: Pydantic schemas + stars mapping

**Files:**
- Create: `api/app/schemas.py`, `api/tests/test_schemas.py`

**Interfaces:**
- Produces (used by ALL later tasks):
  - `Experience(title: str, company: str, start_date: str | None, end_date: str | None, description: str | None)`
  - `Education(degree: str, school: str, year: str | None)`
  - `CVData(full_name: str, email: str | None, phone: str | None, location: str | None, summary: str | None, experiences: list[Experience], education: list[Education], skills: list[str], languages: list[str], certifications: list[str])`
  - `JobCriteria(title: str, company: str | None, requirements: list[str], skills: list[str])`
  - `EvaluationResult(percent: int, stars: int, strengths: list[str], gaps: list[str], suggestions: list[str])`
  - `stars_from_percent(percent: int) -> int`

- [ ] **Step 1: Write the failing test**

`api/tests/test_schemas.py`:
```python
import pytest

from app.schemas import CVData, EvaluationResult, stars_from_percent


@pytest.mark.parametrize("percent,expected", [
    (0, 1), (20, 1), (21, 2), (40, 2), (41, 3), (60, 3),
    (61, 4), (80, 4), (81, 5), (100, 5),
])
def test_stars_from_percent(percent, expected):
    assert stars_from_percent(percent) == expected


def test_cvdata_minimal():
    cv = CVData(full_name="Ada Lovelace")
    assert cv.skills == [] and cv.experiences == []


def test_evaluation_result_bounds():
    with pytest.raises(Exception):
        EvaluationResult(percent=101, stars=5, strengths=[], gaps=[], suggestions=[])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas'`

- [ ] **Step 3: Write minimal implementation**

`api/app/schemas.py`:
```python
from pydantic import BaseModel, Field


def stars_from_percent(percent: int) -> int:
    return min(5, max(1, (percent - 1) // 20 + 1))


class Experience(BaseModel):
    title: str
    company: str
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


class Education(BaseModel):
    degree: str
    school: str
    year: str | None = None


class CVData(BaseModel):
    full_name: str
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    summary: str | None = None
    experiences: list[Experience] = []
    education: list[Education] = []
    skills: list[str] = []
    languages: list[str] = []
    certifications: list[str] = []


class JobCriteria(BaseModel):
    title: str
    company: str | None = None
    requirements: list[str] = []
    skills: list[str] = []


class EvaluationResult(BaseModel):
    percent: int = Field(ge=0, le=100)
    stars: int = Field(ge=1, le=5)
    strengths: list[str] = []
    gaps: list[str] = []
    suggestions: list[str] = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest -v`
Expected: all pass (health + auth + schemas)

- [ ] **Step 5: Commit**

```powershell
git add api
git commit -m "feat(api): core Pydantic schemas + stars mapping"
```

---

### Task 4: PDF text extraction service

**Files:**
- Create: `api/app/services/__init__.py`, `api/app/services/pdf_extract.py`, `api/tests/test_pdf_extract.py`
- Modify: `api/tests/conftest.py` (add `sample_pdf_bytes` fixture)

**Interfaces:**
- Produces: `extract_text(data: bytes) -> str` (raises `ScannedPdfError` when total text < 50 chars; raises `InvalidPdfError` on unparseable bytes). Fixture `sample_pdf_bytes: bytes` (a text PDF containing "Ada Lovelace" and "Python").

- [ ] **Step 1: Write the failing test**

Append to `api/tests/conftest.py`:
```python
from fpdf import FPDF


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
```

`api/tests/test_pdf_extract.py`:
```python
import pytest
from fpdf import FPDF

from app.services.pdf_extract import InvalidPdfError, ScannedPdfError, extract_text


def test_extracts_text(sample_pdf_bytes):
    text = extract_text(sample_pdf_bytes)
    assert "Ada Lovelace" in text
    assert "Python" in text


def test_scanned_pdf_raises():
    pdf = FPDF()
    pdf.add_page()  # empty page, no text
    with pytest.raises(ScannedPdfError):
        extract_text(bytes(pdf.output()))


def test_invalid_bytes_raise():
    with pytest.raises(InvalidPdfError):
        extract_text(b"this is not a pdf")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_pdf_extract.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services'`

- [ ] **Step 3: Write minimal implementation**

Create empty `api/app/services/__init__.py`.

`api/app/services/pdf_extract.py`:
```python
import fitz  # PyMuPDF

MIN_TEXT_CHARS = 50


class InvalidPdfError(Exception):
    pass


class ScannedPdfError(Exception):
    pass


def extract_text(data: bytes) -> str:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise InvalidPdfError(str(exc)) from exc
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    if len(text.strip()) < MIN_TEXT_CHARS:
        raise ScannedPdfError("PDF contains no extractable text")
    return text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest -v`
Expected: all pass

- [ ] **Step 5: Commit**

```powershell
git add api
git commit -m "feat(api): PDF text extraction with scanned/invalid detection"
```

---

### Task 5: LLM wrapper with JSON validation + retry

**Files:**
- Create: `api/app/services/llm.py`, `api/tests/test_llm.py`
- Modify: `api/tests/conftest.py` (add `FakeOpenAI`)

**Interfaces:**
- Produces:
  - `MODEL_FAST = "gpt-4o-mini"`, `MODEL_SMART = "gpt-4o"`
  - `class LLMError(Exception)`
  - `LLMClient(client).chat_json(model: str, system: str, user: str, schema: type[BaseModel]) -> BaseModel` — 1 retry on invalid JSON, then raises `LLMError`
  - `get_llm() -> LLMClient` FastAPI dependency (overridden in endpoint tests)
  - Test helper `FakeOpenAI(contents: list[str])` mimicking `client.chat.completions.create`

- [ ] **Step 1: Write the failing test**

Append to `api/tests/conftest.py`:
```python
from types import SimpleNamespace


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
```

`api/tests/test_llm.py`:
```python
import pytest
from pydantic import BaseModel

from app.services.llm import MODEL_FAST, LLMClient, LLMError
from tests.conftest import FakeOpenAI


class Point(BaseModel):
    x: int
    y: int


def test_valid_json_parsed():
    fake = FakeOpenAI(['{"x": 1, "y": 2}'])
    result = LLMClient(fake).chat_json(MODEL_FAST, "sys", "user", Point)
    assert result == Point(x=1, y=2)
    assert fake.calls[0]["model"] == MODEL_FAST
    assert fake.calls[0]["response_format"] == {"type": "json_object"}


def test_retry_once_on_bad_json():
    fake = FakeOpenAI(["not json", '{"x": 1, "y": 2}'])
    result = LLMClient(fake).chat_json(MODEL_FAST, "sys", "user", Point)
    assert result == Point(x=1, y=2)
    assert len(fake.calls) == 2


def test_raises_after_two_bad():
    fake = FakeOpenAI(["nope", "still nope"])
    with pytest.raises(LLMError):
        LLMClient(fake).chat_json(MODEL_FAST, "sys", "user", Point)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_llm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.llm'`

- [ ] **Step 3: Write minimal implementation**

`api/app/services/llm.py`:
```python
from pydantic import BaseModel, ValidationError

from app.config import get_settings

MODEL_FAST = "gpt-4o-mini"
MODEL_SMART = "gpt-4o"


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, client):
        self._client = client

    def chat_json(self, model: str, system: str, user: str,
                  schema: type[BaseModel]) -> BaseModel:
        for _attempt in range(2):
            resp = self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
            content = resp.choices[0].message.content
            try:
                return schema.model_validate_json(content)
            except ValidationError:
                continue
        raise LLMError("LLM returned invalid JSON twice")


def get_llm() -> LLMClient:
    from openai import OpenAI

    return LLMClient(OpenAI(api_key=get_settings().openai_api_key))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest -v`
Expected: all pass

- [ ] **Step 5: Commit**

```powershell
git add api
git commit -m "feat(api): LLM client wrapper with JSON validation and retry"
```

---

### Task 6: Daily usage limiter

**Files:**
- Create: `api/app/services/usage.py`, `api/tests/test_usage.py`
- Modify: `api/tests/conftest.py` (add autouse reset fixture)

**Interfaces:**
- Produces: `UsageStore` (in-memory, per user per UTC day), module-level singleton `usage_store`, and FastAPI dependency `check_usage(user_id: str = Depends(get_current_user)) -> str` that raises 429 `{"code": "DAILY_LIMIT_REACHED"}` past the limit and returns `user_id` otherwise. LLM endpoints depend on `check_usage` INSTEAD of `get_current_user` (it chains it).

- [ ] **Step 1: Write the failing test**

`api/tests/test_usage.py`:
```python
import pytest
from fastapi import HTTPException

from app.services.usage import UsageStore, enforce_limit


def test_allows_up_to_limit():
    store = UsageStore()
    for _ in range(20):
        enforce_limit(store, "u1", limit=20)  # must not raise


def test_blocks_past_limit():
    store = UsageStore()
    for _ in range(20):
        enforce_limit(store, "u1", limit=20)
    with pytest.raises(HTTPException) as exc:
        enforce_limit(store, "u1", limit=20)
    assert exc.value.status_code == 429
    assert exc.value.detail == {"code": "DAILY_LIMIT_REACHED"}


def test_users_are_independent():
    store = UsageStore()
    for _ in range(20):
        enforce_limit(store, "u1", limit=20)
    enforce_limit(store, "u2", limit=20)  # different user, must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_usage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.usage'`

- [ ] **Step 3: Write minimal implementation**

`api/app/services/usage.py`:
```python
from collections import defaultdict
from datetime import date

from fastapi import Depends, HTTPException

from app.auth import get_current_user
from app.config import get_settings


class UsageStore:
    """In-memory daily counter. Swap for a DB-backed store in Plan 2."""

    def __init__(self):
        self._counts: dict[tuple[str, str], int] = defaultdict(int)

    def increment(self, user_id: str) -> int:
        key = (user_id, date.today().isoformat())
        self._counts[key] += 1
        return self._counts[key]


usage_store = UsageStore()


def enforce_limit(store: UsageStore, user_id: str, limit: int) -> None:
    if store.increment(user_id) > limit:
        raise HTTPException(status_code=429, detail={"code": "DAILY_LIMIT_REACHED"})


def check_usage(user_id: str = Depends(get_current_user)) -> str:
    enforce_limit(usage_store, user_id, get_settings().daily_ai_limit)
    return user_id
```

Append to `api/tests/conftest.py` (prevents endpoint tests from eating into the daily limit across the suite):
```python
@pytest.fixture(autouse=True)
def _reset_usage():
    from app.services.usage import usage_store
    usage_store._counts.clear()
    yield
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest -v`
Expected: all pass

- [ ] **Step 5: Commit**

```powershell
git add api
git commit -m "feat(api): daily AI usage limiter"
```

---

### Task 7: CV parser service + POST /cv/parse

**Files:**
- Create: `api/app/services/cv_parser.py`, `api/app/routers/__init__.py`, `api/app/routers/cv.py`, `api/tests/test_cv_parse.py`
- Modify: `api/app/main.py` (include router), `api/tests/conftest.py` (add `SAMPLE_CV_JSON` + `override_llm` helper)

**Interfaces:**
- Consumes: `extract_text`, `LLMClient.chat_json`, `MODEL_FAST`, `CVData`, `check_usage`, `get_llm`.
- Produces: `parse_cv(text: str, llm: LLMClient) -> CVData`; endpoint `POST /cv/parse` (multipart `file`) → 200 `{"cv": CVData}`; 400 `{"code": "SCANNED_PDF"}` / `{"code": "INVALID_PDF"}` / `{"code": "FILE_TOO_LARGE"}`; conftest constant `SAMPLE_CV_JSON: str` and helper `override_llm(contents: list[str]) -> FakeOpenAI`.

- [ ] **Step 1: Write the failing test**

Append to `api/tests/conftest.py`:
```python
import json

from app.main import app as _app
from app.services.llm import LLMClient, get_llm

SAMPLE_CV_JSON = json.dumps({
    "full_name": "Ada Lovelace",
    "email": "ada@example.com",
    "phone": None,
    "location": "London",
    "summary": "Software engineer with analytical background.",
    "experiences": [{"title": "Developer", "company": "Analytical Engine Corp",
                     "start_date": "2020", "end_date": "2024",
                     "description": "Built compute engines."}],
    "education": [{"degree": "BSc Mathematics", "school": "Cambridge", "year": "2019"}],
    "skills": ["Python", "SQL", "FastAPI"],
    "languages": ["English", "Turkish"],
    "certifications": [],
})


def override_llm(contents: list[str]) -> FakeOpenAI:
    fake = FakeOpenAI(contents)
    _app.dependency_overrides[get_llm] = lambda: LLMClient(fake)
    return fake


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    _app.dependency_overrides.clear()
```

`api/tests/test_cv_parse.py`:
```python
from fpdf import FPDF

from tests.conftest import SAMPLE_CV_JSON, override_llm


def test_parse_cv_success(client, auth_headers, sample_pdf_bytes):
    override_llm([SAMPLE_CV_JSON])
    r = client.post("/cv/parse", headers=auth_headers,
                    files={"file": ("cv.pdf", sample_pdf_bytes, "application/pdf")})
    assert r.status_code == 200
    cv = r.json()["cv"]
    assert cv["full_name"] == "Ada Lovelace"
    assert "Python" in cv["skills"]


def test_scanned_pdf_rejected(client, auth_headers):
    pdf = FPDF(); pdf.add_page()
    r = client.post("/cv/parse", headers=auth_headers,
                    files={"file": ("cv.pdf", bytes(pdf.output()), "application/pdf")})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "SCANNED_PDF"


def test_invalid_pdf_rejected(client, auth_headers):
    r = client.post("/cv/parse", headers=auth_headers,
                    files={"file": ("cv.pdf", b"not a pdf", "application/pdf")})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "INVALID_PDF"


def test_oversize_rejected(client, auth_headers):
    big = b"x" * (10 * 1024 * 1024 + 1)
    r = client.post("/cv/parse", headers=auth_headers,
                    files={"file": ("cv.pdf", big, "application/pdf")})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "FILE_TOO_LARGE"


def test_requires_auth(client, sample_pdf_bytes):
    r = client.post("/cv/parse",
                    files={"file": ("cv.pdf", sample_pdf_bytes, "application/pdf")})
    assert r.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_cv_parse.py -v`
Expected: FAIL — 404 (route not registered) or import error

- [ ] **Step 3: Write minimal implementation**

`api/app/services/cv_parser.py`:
```python
from app.schemas import CVData
from app.services.llm import MODEL_FAST, LLMClient

SYSTEM = (
    "You are a CV parser. Extract structured data from the CV text. "
    "Respond ONLY with JSON matching this schema: "
    '{"full_name": str, "email": str|null, "phone": str|null, '
    '"location": str|null, "summary": str|null, '
    '"experiences": [{"title": str, "company": str, "start_date": str|null, '
    '"end_date": str|null, "description": str|null}], '
    '"education": [{"degree": str, "school": str, "year": str|null}], '
    '"skills": [str], "languages": [str], "certifications": [str]}. '
    "Keep the CV's original language. Do not invent information."
)


def parse_cv(text: str, llm: LLMClient) -> CVData:
    return llm.chat_json(MODEL_FAST, SYSTEM, text, CVData)
```

Create empty `api/app/routers/__init__.py`.

`api/app/routers/cv.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.services.cv_parser import parse_cv
from app.services.llm import LLMClient, get_llm
from app.services.pdf_extract import InvalidPdfError, ScannedPdfError, extract_text
from app.services.usage import check_usage

MAX_SIZE = 10 * 1024 * 1024

router = APIRouter(prefix="/cv", tags=["cv"])


@router.post("/parse")
async def cv_parse(
    file: UploadFile,
    user_id: str = Depends(check_usage),
    llm: LLMClient = Depends(get_llm),
):
    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=400, detail={"code": "FILE_TOO_LARGE"})
    try:
        text = extract_text(data)
    except ScannedPdfError:
        raise HTTPException(status_code=400, detail={"code": "SCANNED_PDF"})
    except InvalidPdfError:
        raise HTTPException(status_code=400, detail={"code": "INVALID_PDF"})
    cv = parse_cv(text, llm)
    return {"cv": cv}
```

In `api/app/main.py`, add:
```python
from app.routers import cv as cv_router

app.include_router(cv_router.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest -v`
Expected: all pass

- [ ] **Step 5: Commit**

```powershell
git add api
git commit -m "feat(api): CV parse endpoint with PDF validation"
```

---

### Task 8: Job fetch service + POST /job/fetch

**Files:**
- Create: `api/app/services/job_fetch.py`, `api/app/routers/job.py`, `api/tests/test_job_fetch.py`
- Modify: `api/app/main.py` (include router)

**Interfaces:**
- Consumes: `LLMClient`, `MODEL_FAST`, `JobCriteria`, `check_usage`, `get_llm`.
- Produces: `fetch_job_text(url: str) -> str | None` (None = blocked/failed); `extract_criteria(text: str, llm: LLMClient) -> JobCriteria`; endpoint `POST /job/fetch` body `{"url": str | null, "text": str | null}` → 200 `{"criteria": JobCriteria, "description": str, "fetch_method": "url"|"manual"}`; 422 `{"code": "FETCH_FAILED"}` when URL fetch fails; 422 `{"code": "NO_INPUT"}` when both fields empty.

- [ ] **Step 1: Write the failing test**

`api/tests/test_job_fetch.py`:
```python
import json

from app.services import job_fetch
from tests.conftest import override_llm

CRITERIA_JSON = json.dumps({
    "title": "Backend Developer",
    "company": "Acme",
    "requirements": ["3+ years Python", "REST API design"],
    "skills": ["Python", "FastAPI", "PostgreSQL"],
})


def test_fetch_from_url(client, auth_headers, monkeypatch):
    monkeypatch.setattr(job_fetch, "fetch_job_text",
                        lambda url: "We are hiring a Backend Developer...")
    override_llm([CRITERIA_JSON])
    r = client.post("/job/fetch", headers=auth_headers,
                    json={"url": "https://example.com/job/1"})
    assert r.status_code == 200
    body = r.json()
    assert body["fetch_method"] == "url"
    assert body["criteria"]["title"] == "Backend Developer"


def test_fetch_failure_returns_code(client, auth_headers, monkeypatch):
    monkeypatch.setattr(job_fetch, "fetch_job_text", lambda url: None)
    r = client.post("/job/fetch", headers=auth_headers,
                    json={"url": "https://linkedin.com/jobs/1"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "FETCH_FAILED"


def test_manual_text(client, auth_headers):
    override_llm([CRITERIA_JSON])
    r = client.post("/job/fetch", headers=auth_headers,
                    json={"text": "We are hiring a Backend Developer..."})
    assert r.status_code == 200
    assert r.json()["fetch_method"] == "manual"


def test_no_input(client, auth_headers):
    r = client.post("/job/fetch", headers=auth_headers, json={})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "NO_INPUT"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_job_fetch.py -v`
Expected: FAIL — import error on `app.services.job_fetch`

- [ ] **Step 3: Write minimal implementation**

`api/app/services/job_fetch.py`:
```python
import httpx
import trafilatura

from app.schemas import JobCriteria
from app.services.llm import MODEL_FAST, LLMClient

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

SYSTEM = (
    "You extract job posting criteria. Respond ONLY with JSON: "
    '{"title": str, "company": str|null, "requirements": [str], "skills": [str]}. '
    "requirements = qualifications/experience asked for; skills = concrete tools/technologies."
)


def fetch_job_text(url: str) -> str | None:
    try:
        resp = httpx.get(url, headers={"User-Agent": UA},
                         follow_redirects=True, timeout=15)
        if resp.status_code != 200:
            return None
        text = trafilatura.extract(resp.text)
        return text if text and len(text) > 100 else None
    except httpx.HTTPError:
        return None


def extract_criteria(text: str, llm: LLMClient) -> JobCriteria:
    return llm.chat_json(MODEL_FAST, SYSTEM, text, JobCriteria)
```

`api/app/routers/job.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services import job_fetch
from app.services.llm import LLMClient, get_llm
from app.services.usage import check_usage

router = APIRouter(prefix="/job", tags=["job"])


class JobFetchRequest(BaseModel):
    url: str | None = None
    text: str | None = None


@router.post("/fetch")
def fetch(
    req: JobFetchRequest,
    user_id: str = Depends(check_usage),
    llm: LLMClient = Depends(get_llm),
):
    if req.text:
        description, method = req.text, "manual"
    elif req.url:
        fetched = job_fetch.fetch_job_text(req.url)
        if fetched is None:
            raise HTTPException(status_code=422, detail={"code": "FETCH_FAILED"})
        description, method = fetched, "url"
    else:
        raise HTTPException(status_code=422, detail={"code": "NO_INPUT"})
    criteria = job_fetch.extract_criteria(description, llm)
    return {"criteria": criteria, "description": description, "fetch_method": method}
```

In `api/app/main.py`, add:
```python
from app.routers import job as job_router

app.include_router(job_router.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest -v`
Expected: all pass

- [ ] **Step 5: Commit**

```powershell
git add api
git commit -m "feat(api): job posting fetch with manual-paste fallback"
```

---

### Task 9: Scorer service + POST /score

**Files:**
- Create: `api/app/services/scorer.py`, `api/app/routers/score.py`, `api/tests/test_score.py`
- Modify: `api/app/main.py` (include router)

**Interfaces:**
- Consumes: `CVData`, `JobCriteria`, `EvaluationResult`, `stars_from_percent`, `LLMClient`, `MODEL_SMART`, `check_usage`, `get_llm`, conftest `SAMPLE_CV_JSON`.
- Produces: `score_cv(cv: CVData, job: JobCriteria, llm: LLMClient) -> EvaluationResult` (stars computed server-side); endpoint `POST /score` body `{"cv": CVData, "job": JobCriteria}` → 200 `EvaluationResult`.

- [ ] **Step 1: Write the failing test**

`api/tests/test_score.py`:
```python
import json

from tests.conftest import SAMPLE_CV_JSON, override_llm

JOB = {"title": "Backend Developer", "company": "Acme",
       "requirements": ["3+ years Python"], "skills": ["Python", "FastAPI"]}

LLM_SCORE = json.dumps({
    "percent": 78,
    "strengths": ["Strong Python background", "FastAPI experience"],
    "gaps": ["No PostgreSQL mentioned"],
    "suggestions": ["Add database projects to CV"],
})


def test_score_returns_evaluation(client, auth_headers):
    override_llm([LLM_SCORE])
    r = client.post("/score", headers=auth_headers,
                    json={"cv": json.loads(SAMPLE_CV_JSON), "job": JOB})
    assert r.status_code == 200
    body = r.json()
    assert body["percent"] == 78
    assert body["stars"] == 4  # 61-80 -> 4, computed server-side
    assert body["strengths"] and body["gaps"] and body["suggestions"]


def test_stars_never_from_llm(client, auth_headers):
    # even if LLM tried to sneak stars in, percent drives the mapping
    payload = json.loads(LLM_SCORE); payload["percent"] = 95
    override_llm([json.dumps(payload)])
    r = client.post("/score", headers=auth_headers,
                    json={"cv": json.loads(SAMPLE_CV_JSON), "job": JOB})
    assert r.json()["stars"] == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_score.py -v`
Expected: FAIL — 404 or import error

- [ ] **Step 3: Write minimal implementation**

`api/app/services/scorer.py`:
```python
from pydantic import BaseModel, Field

from app.schemas import CVData, EvaluationResult, JobCriteria, stars_from_percent
from app.services.llm import MODEL_SMART, LLMClient

SYSTEM = (
    "You score how well a CV fits a job posting. Use this fixed rubric: "
    "skills match 40%, experience relevance 35%, education/other 25%. "
    "Respond ONLY with JSON: "
    '{"percent": int 0-100, "strengths": [str], "gaps": [str], "suggestions": [str]}. '
    "strengths = where the CV matches the criteria; gaps = missing criteria; "
    "suggestions = concrete CV improvements. "
    "Write strengths/gaps/suggestions in the CV's language."
)


class _ScoreOut(BaseModel):
    percent: int = Field(ge=0, le=100)
    strengths: list[str] = []
    gaps: list[str] = []
    suggestions: list[str] = []


def score_cv(cv: CVData, job: JobCriteria, llm: LLMClient) -> EvaluationResult:
    user = f"CV:\n{cv.model_dump_json()}\n\nJOB POSTING:\n{job.model_dump_json()}"
    out = llm.chat_json(MODEL_SMART, SYSTEM, user, _ScoreOut)
    return EvaluationResult(
        percent=out.percent,
        stars=stars_from_percent(out.percent),
        strengths=out.strengths,
        gaps=out.gaps,
        suggestions=out.suggestions,
    )
```

`api/app/routers/score.py`:
```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.schemas import CVData, EvaluationResult, JobCriteria
from app.services.llm import LLMClient, get_llm
from app.services.scorer import score_cv
from app.services.usage import check_usage

router = APIRouter(tags=["score"])


class ScoreRequest(BaseModel):
    cv: CVData
    job: JobCriteria


@router.post("/score", response_model=EvaluationResult)
def score(
    req: ScoreRequest,
    user_id: str = Depends(check_usage),
    llm: LLMClient = Depends(get_llm),
):
    return score_cv(req.cv, req.job, llm)
```

In `api/app/main.py`, add:
```python
from app.routers import score as score_router

app.include_router(score_router.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest -v`
Expected: all pass

- [ ] **Step 5: Commit**

```powershell
git add api
git commit -m "feat(api): rubric-based CV-job scoring endpoint"
```

---

### Task 10: ATS rewrite + PDF render + endpoints

**Files:**
- Create: `api/app/services/ats.py`, `api/app/routers/ats.py`, `api/tests/test_ats.py`
- Modify: `api/app/main.py` (include router), `docs/superpowers/specs/2026-07-12-cv-ai-mvp-design.md` (WeasyPrint → fpdf2 note)

**Interfaces:**
- Consumes: `CVData`, `LLMClient`, `MODEL_SMART`, `check_usage`, `get_current_user`, `get_llm`, conftest `SAMPLE_CV_JSON`.
- Produces: `rewrite_ats(cv: CVData, language: str, llm: LLMClient) -> CVData`; `render_pdf(cv: CVData, language: str) -> bytes`; `POST /ats/rewrite` body `{"cv": CVData, "language": "tr"|"en"}` → `{"cv": CVData}` (uses `check_usage`); `POST /ats/pdf` same body → PDF bytes (`application/pdf`, no LLM ⇒ only `get_current_user`).

- [ ] **Step 1: Write the failing test**

`api/tests/test_ats.py`:
```python
import json

from app.schemas import CVData
from app.services.ats import render_pdf
from tests.conftest import SAMPLE_CV_JSON, override_llm


def _cv() -> CVData:
    return CVData.model_validate_json(SAMPLE_CV_JSON)


def test_render_pdf_produces_pdf():
    pdf = render_pdf(_cv(), "en")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


def test_render_pdf_turkish_chars():
    cv = _cv()
    cv.full_name = "Şükrü Çağrı Öğüt"
    cv.summary = "Gömülü yazılım geliştirici; İstanbul'da 5 yıl deneyim."
    pdf = render_pdf(cv, "tr")
    assert pdf.startswith(b"%PDF")


def test_rewrite_endpoint(client, auth_headers):
    override_llm([SAMPLE_CV_JSON])  # fake LLM returns rewritten CV
    r = client.post("/ats/rewrite", headers=auth_headers,
                    json={"cv": json.loads(SAMPLE_CV_JSON), "language": "en"})
    assert r.status_code == 200
    assert r.json()["cv"]["full_name"] == "Ada Lovelace"


def test_pdf_endpoint(client, auth_headers):
    r = client.post("/ats/pdf", headers=auth_headers,
                    json={"cv": json.loads(SAMPLE_CV_JSON), "language": "tr"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_ats.py -v`
Expected: FAIL — import error on `app.services.ats`

- [ ] **Step 3: Write minimal implementation**

`api/app/services/ats.py`:
```python
from pathlib import Path

from fpdf import FPDF

from app.schemas import CVData
from app.services.llm import MODEL_SMART, LLMClient

SYSTEM = (
    "You rewrite CVs to be ATS-compliant. Rules: standard section wording, "
    "concise bullet-style descriptions, measurable achievements where the "
    "original supports them, no invented facts, no tables/graphics/icons. "
    "Answer in language: {language}. Respond ONLY with JSON in the same CV schema "
    "you received."
)

HEADINGS = {
    "tr": {"summary": "ÖZET", "experience": "İŞ DENEYİMİ", "education": "EĞİTİM",
           "skills": "BECERİLER", "languages": "DİLLER", "certifications": "SERTİFİKALAR"},
    "en": {"summary": "SUMMARY", "experience": "EXPERIENCE", "education": "EDUCATION",
           "skills": "SKILLS", "languages": "LANGUAGES", "certifications": "CERTIFICATIONS"},
}

_FONT_CANDIDATES = [
    (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]


def _find_fonts() -> tuple[str, str]:
    for regular, bold in _FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            return regular, bold
    raise RuntimeError("No Unicode TTF font found; set font paths in ats.py")


def rewrite_ats(cv: CVData, language: str, llm: LLMClient) -> CVData:
    return llm.chat_json(MODEL_SMART, SYSTEM.format(language=language),
                         cv.model_dump_json(), CVData)


def render_pdf(cv: CVData, language: str) -> bytes:
    h = HEADINGS.get(language, HEADINGS["en"])
    regular, bold = _find_fonts()
    pdf = FPDF()
    pdf.add_font("Main", "", regular)
    pdf.add_font("Main", "B", bold)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def heading(text: str):
        pdf.set_font("Main", "B", 13)
        pdf.cell(0, 9, text, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Main", "", 10.5)

    def line(text: str):
        pdf.multi_cell(0, 5.5, text)

    pdf.set_font("Main", "B", 17)
    pdf.cell(0, 10, cv.full_name, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Main", "", 10)
    contact = " | ".join(x for x in [cv.email, cv.phone, cv.location] if x)
    if contact:
        line(contact)
    pdf.ln(3)

    if cv.summary:
        heading(h["summary"]); line(cv.summary); pdf.ln(2)
    if cv.experiences:
        heading(h["experience"])
        for e in cv.experiences:
            pdf.set_font("Main", "B", 10.5)
            dates = f" ({e.start_date or ''} - {e.end_date or ''})".replace("( - )", "")
            line(f"{e.title} — {e.company}{dates}")
            pdf.set_font("Main", "", 10.5)
            if e.description:
                line(e.description)
        pdf.ln(2)
    if cv.education:
        heading(h["education"])
        for ed in cv.education:
            line(f"{ed.degree} — {ed.school}" + (f" ({ed.year})" if ed.year else ""))
        pdf.ln(2)
    if cv.skills:
        heading(h["skills"]); line(", ".join(cv.skills)); pdf.ln(2)
    if cv.languages:
        heading(h["languages"]); line(", ".join(cv.languages)); pdf.ln(2)
    if cv.certifications:
        heading(h["certifications"]); line(", ".join(cv.certifications))

    return bytes(pdf.output())
```

`api/app/routers/ats.py`:
```python
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from app.auth import get_current_user
from app.schemas import CVData
from app.services.ats import render_pdf, rewrite_ats
from app.services.llm import LLMClient, get_llm
from app.services.usage import check_usage

router = APIRouter(prefix="/ats", tags=["ats"])


class AtsRequest(BaseModel):
    cv: CVData
    language: str = "tr"


@router.post("/rewrite")
def rewrite(
    req: AtsRequest,
    user_id: str = Depends(check_usage),
    llm: LLMClient = Depends(get_llm),
):
    return {"cv": rewrite_ats(req.cv, req.language, llm)}


@router.post("/pdf")
def pdf(req: AtsRequest, user_id: str = Depends(get_current_user)):
    data = render_pdf(req.cv, req.language)
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="cv-ats.pdf"'})
```

In `api/app/main.py`, add:
```python
from app.routers import ats as ats_router

app.include_router(ats_router.router)
```

In `docs/superpowers/specs/2026-07-12-cv-ai-mvp-design.md`, change the row
`| PDF üretme | WeasyPrint | HTML→PDF, ATS şablonu için ideal |` to:
`| PDF üretme | fpdf2 | saf Python; WeasyPrint'in GTK bağımlılığı Windows'ta sorunlu olduğu için değiştirildi |`

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest -v`
Expected: all pass

- [ ] **Step 5: Commit**

```powershell
git add api docs
git commit -m "feat(api): ATS rewrite and Unicode PDF rendering endpoints"
```

---

### Task 11: CORS + LLM error handler + README + full suite

**Files:**
- Create: `api/README.md`, `api/tests/test_llm_error_handling.py`
- Modify: `api/app/main.py` (CORS + exception handler)

**Interfaces:**
- Consumes: everything above.
- Produces: CORS for `http://localhost:3000` (Plan 2 frontend); global handler mapping `LLMError` → 502 `{"code": "AI_UNAVAILABLE"}`; `README.md` with run instructions.

- [ ] **Step 1: Write the failing test**

`api/tests/test_llm_error_handling.py`:
```python
import json

from tests.conftest import SAMPLE_CV_JSON, override_llm

JOB = {"title": "Dev", "company": None, "requirements": [], "skills": []}


def test_llm_failure_returns_502(client, auth_headers):
    override_llm(["broken", "still broken"])  # both attempts invalid
    r = client.post("/score", headers=auth_headers,
                    json={"cv": json.loads(SAMPLE_CV_JSON), "job": JOB})
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "AI_UNAVAILABLE"


def test_cors_preflight(client):
    r = client.options("/score", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
    })
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_llm_error_handling.py -v`
Expected: FAIL — 500 instead of 502; missing CORS headers

- [ ] **Step 3: Write minimal implementation**

Update `api/app/main.py` to its final form:
```python
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import ats as ats_router
from app.routers import cv as cv_router
from app.routers import job as job_router
from app.routers import score as score_router
from app.services.llm import LLMError

app = FastAPI(title="CV-AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(LLMError)
def llm_error_handler(request: Request, exc: LLMError):
    return JSONResponse(status_code=502,
                        content={"detail": {"code": "AI_UNAVAILABLE"}})


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(cv_router.router)
app.include_router(job_router.router)
app.include_router(score_router.router)
app.include_router(ats_router.router)
```

`api/README.md`:
```markdown
# CV-AI API

FastAPI backend: CV parsing, job-fit scoring, ATS conversion.

## Setup
    python -m venv .venv
    .venv\Scripts\pip install -r requirements.txt
    copy .env.example .env   # fill in OPENAI_API_KEY, SUPABASE_JWT_SECRET

## Run
    .venv\Scripts\uvicorn app.main:app --reload --port 8000

## Test
    .venv\Scripts\python -m pytest -v

Endpoints: POST /cv/parse, /job/fetch, /score, /ats/rewrite, /ats/pdf (all JWT-protected).
```

- [ ] **Step 4: Run full suite to verify everything passes**

Run: `.venv\Scripts\python -m pytest -v`
Expected: ALL tests pass (≈30 tests)

- [ ] **Step 5: Commit**

```powershell
git add api
git commit -m "feat(api): CORS, LLM error handling, README"
```
