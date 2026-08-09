# ATS CV Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/ats/rewrite` and `/apply/prepare` produce ATS CVs under one shared rule set, with a schema rich enough to hold projects, achievements, structured certifications and per-experience bullets.

**Architecture:** A new `app/services/ats_prompt.py` owns the rule text and composes two system prompts from it — one posting-free (`/ats/rewrite`), one posting-aware (`/apply/prepare`). `CVData` grows additively so stored `parsed_data` JSON keeps loading. The PDF renderer gains the new sections and the left-aligned contact layout. Three web surfaces render the new data.

**Tech Stack:** FastAPI + Pydantic v2 + pytest (`api/`), Next.js + next-intl + vitest (`web/`), fpdf2 for PDF, pymupdf for PDF assertions in tests.

**Spec:** `docs/superpowers/specs/2026-08-09-ats-cv-engine-design.md`

## Global Constraints

- Branch: `feat/ats-cv-engine`. It already exists and holds the spec commit.
- Every prompt and every source file is written in English. Output language stays governed by the `language` parameter — Turkish CVs keep coming out Turkish.
- No existing `CVData` field may be removed, and every field must keep parsing data already stored in Supabase `cvs.parsed_data`.
- Commit messages carry no `Co-Authored-By` and no `Claude-Session` trailer.
- API tests run from `api/` with `.venv\Scripts\python -m pytest`. Web tests run from `web/` with `npm test`. Windows: run Next.js commands from `C:\Users\ASUS\Desktop\cv-ai\web` (capital `D` in `Desktop`).
- Prompt strings built in `ats_prompt.py` must NOT use `str.format()`. They contain literal JSON braces; f-string composition avoids the `{{`/`}}` escaping that `apply.py:30` currently needs.
- Never run `git commit --no-verify`.

---

### Task 1: Extend the CV schema

**Files:**
- Modify: `api/app/schemas.py:8-47`
- Test: `api/tests/test_schemas.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Project(name: str, kind: str | None, technologies: list[str], bullets: list[str])`, `Certification(name: str, issuer: str | None, date: str | None)`, `Experience.location: str | None`, `Experience.bullets: list[str]`, `Education.location: str | None`, `Education.start_date: str | None`, `Education.details: list[str]`, `CVData.projects: list[Project]`, `CVData.achievements: list[str]`, `CVData.certifications: list[Certification]`.

- [ ] **Step 1: Write the failing tests**

Append to `api/tests/test_schemas.py`:

```python
from app.schemas import CVData, Certification, Project


LEGACY_CV = {
    "full_name": "Ada Lovelace",
    "summary": "Engineer.",
    "experiences": [{"title": "Developer", "company": "Analytical Engine Corp",
                     "start_date": "2020", "end_date": "2024",
                     "description": "Built compute engines."}],
    "education": [{"degree": "BSc Mathematics", "school": "Cambridge", "year": "2019"}],
    "skills": ["Python"],
    "languages": ["English"],
    "certifications": ["AWS Solutions Architect", "Scrum Master"],
}


def test_legacy_parsed_data_still_loads():
    cv = CVData.model_validate(LEGACY_CV)
    assert cv.experiences[0].description == "Built compute engines."
    assert cv.experiences[0].bullets == []
    assert cv.experiences[0].location is None
    assert cv.projects == []
    assert cv.achievements == []


def test_legacy_string_certifications_are_coerced():
    cv = CVData.model_validate(LEGACY_CV)
    assert cv.certifications[0] == Certification(name="AWS Solutions Architect")
    assert cv.certifications[1].issuer is None
    assert cv.certifications[1].date is None


def test_structured_certifications_load():
    cv = CVData.model_validate({
        **LEGACY_CV,
        "certifications": [{"name": "AWS SAA", "issuer": "Amazon", "date": "Mar 2024"}],
    })
    assert cv.certifications[0].issuer == "Amazon"
    assert cv.certifications[0].date == "Mar 2024"


def test_projects_and_achievements_load():
    cv = CVData.model_validate({
        **LEGACY_CV,
        "projects": [{"name": "Bombe", "kind": "academic",
                      "technologies": ["Python"], "bullets": ["Cracked ciphers."]}],
        "achievements": ["Best paper award, 1843"],
    })
    assert cv.projects[0] == Project(name="Bombe", kind="academic",
                                     technologies=["Python"], bullets=["Cracked ciphers."])
    assert cv.achievements == ["Best paper award, 1843"]


def test_education_and_experience_details_load():
    cv = CVData.model_validate({
        **LEGACY_CV,
        "experiences": [{"title": "Developer", "company": "Acme",
                         "location": "İstanbul, Türkiye",
                         "start_date": "Oca 2024", "end_date": "Devam Ediyor",
                         "bullets": ["Designed REST APIs.", "Tuned SQL queries."]}],
        "education": [{"degree": "BSc", "school": "Cambridge", "location": "Cambridge, UK",
                       "start_date": "2015", "year": "2019",
                       "details": ["GPA 3.8/4.0", "Thesis on analytical engines"]}],
    })
    assert cv.experiences[0].location == "İstanbul, Türkiye"
    assert cv.experiences[0].bullets == ["Designed REST APIs.", "Tuned SQL queries."]
    assert cv.education[0].details == ["GPA 3.8/4.0", "Thesis on analytical engines"]
    assert cv.education[0].start_date == "2015"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\api && .venv\Scripts\python -m pytest tests/test_schemas.py -v`
Expected: FAIL — `ImportError: cannot import name 'Certification'`.

- [ ] **Step 3: Write the implementation**

In `api/app/schemas.py`, add `field_validator` to the pydantic import, add the two models above `CVData`, and extend the existing ones:

```python
from pydantic import AliasChoices, BaseModel, Field, field_validator


class Experience(BaseModel):
    title: str
    company: str
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    # Legacy free-text description. Rows written before the ATS engine have this
    # set and `bullets` empty; the renderer falls back to it. The rewrite always
    # fills `bullets`.
    description: str | None = None
    bullets: list[str] = []


class Education(BaseModel):
    degree: str | None = None
    school: str
    location: str | None = None
    start_date: str | None = None
    year: str | None = None
    # GPA, honours, scholarship, thesis — whichever the source CV actually has.
    # A flat list rather than a field per concept, so no field invites filling.
    details: list[str] = []


class Project(BaseModel):
    name: str
    # academic | personal | freelance | professional. Its own field because the
    # accuracy rules forbid presenting an academic project as client work, and a
    # field is something a test can assert on.
    kind: str | None = None
    technologies: list[str] = []
    bullets: list[str] = []


class Certification(BaseModel):
    name: str
    issuer: str | None = None
    date: str | None = None
```

In `CVData`, replace the `certifications` line and add the two new fields:

```python
    projects: list[Project] = []
    achievements: list[str] = []
    languages: list[str] = []
    certifications: list[Certification] = []

    @field_validator("certifications", mode="before")
    @classmethod
    def _coerce_certifications(cls, value):
        # Rows written before the ATS engine store certifications as plain
        # strings. Coercing here keeps every stored CV loadable without a
        # migration, and without a second field holding the same fact.
        if isinstance(value, list):
            return [{"name": v} if isinstance(v, str) else v for v in value]
        return value
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\api && .venv\Scripts\python -m pytest tests/test_schemas.py -v`
Expected: PASS.

- [ ] **Step 5: Run the whole API suite**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\api && .venv\Scripts\python -m pytest -q`
Expected: PASS. `test_ats.py` and `test_cv_parse.py` still pass — `SAMPLE_CV_JSON` has `"certifications": []`, which the validator leaves untouched.

- [ ] **Step 6: Commit**

```bash
git add api/app/schemas.py api/tests/test_schemas.py
git commit -m "feat(api): hold projects, achievements and structured certifications in CVData"
```

---

### Task 2: The shared ATS rule set

**Files:**
- Create: `api/app/services/ats_prompt.py`
- Test: `api/tests/test_ats_prompt.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ATS_RULES: str`, `build_rewrite_system(language: str) -> str`, `build_apply_system(language: str) -> str`.

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_ats_prompt.py`:

```python
from app.services.ats_prompt import ATS_RULES, build_apply_system, build_rewrite_system


def test_both_prompts_carry_the_shared_rules():
    assert ATS_RULES in build_rewrite_system("tr")
    assert ATS_RULES in build_apply_system("tr")


def test_rewrite_prompt_has_no_posting_block():
    system = build_rewrite_system("en")
    assert "job_text" not in system
    assert "form" not in system
    assert "verification_required" in system
    assert "optimization_summary" in system


def test_apply_prompt_has_the_posting_and_form_contract():
    system = build_apply_system("en")
    assert "job_text" in system
    assert "field_id" in system
    assert "cover_letter" in system
    assert "verification_required" in system


def test_language_is_injected():
    assert "Answer in language: tr." in build_rewrite_system("tr")
    assert "Answer in language: en." in build_apply_system("en")


def test_prompts_contain_no_unformatted_placeholders():
    # These strings are composed with f-strings, never str.format(). A stray
    # doubled brace would reach the model verbatim.
    for system in (build_rewrite_system("tr"), build_apply_system("tr")):
        assert "{{" not in system
        assert "{language}" not in system


def test_accuracy_rules_lead_the_prompt():
    # The rules the model most needs to obey must not sit behind 2,000 words of
    # formatting guidance.
    assert ATS_RULES.index("ACCURACY") < ATS_RULES.index("STRUCTURE")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\api && .venv\Scripts\python -m pytest tests/test_ats_prompt.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.ats_prompt'`.

- [ ] **Step 3: Write the implementation**

Create `api/app/services/ats_prompt.py`:

```python
"""The ATS rule set, shared by the standalone rewrite and the assisted apply.

Both flows produce a CV for a machine to parse and a recruiter to skim. Keeping
one rule text means the assisted flow cannot drift into a lower standard than
the ATS page, which is exactly what happened while each had its own prompt.

Composed with f-strings, never str.format(): the output contracts below contain
literal JSON braces, and escaping them is a footgun that has already bitten the
apply prompt.
"""

ATS_RULES = """You convert a CV into a clean, single-column, ATS-compliant CV.
Preserve the real information in the source; improve only its structure, wording and ordering.

ACCURACY — these override every other rule:
1. Never state anything the source CV does not contain.
2. Never add a company, role, project, technology, duty, degree, certificate, achievement, date or number.
3. Never raise the candidate's seniority or exaggerate the scope of their work.
4. Never present an internship as full-time employment.
5. Never present an academic or personal project as commercial client work.
6. Never estimate a missing metric or success rate.
7. Never turn vague information into precise information.
8. When you are unsure, leave it out of the CV and record it in verification_required instead of guessing.
9. Copy contact details, links, organisation names, dates and proper nouns through unchanged.
10. Fix spelling and grammar, but never change the meaning of a proper noun.
11. Never repeat the same fact in two sections.
12. Use a posting's keywords only where the candidate's own history supports them.

STRUCTURE
Standard section names, logical top-to-bottom order, plain bullets, no decorative symbols.
Fill only the sections the source supports; leave the rest empty rather than padding them.
Emphasise experience for experienced candidates, education and projects for new graduates, skills and projects for technical roles.

CONTACT
Keep full_name, title, location, phone, email, linkedin, github and website exactly as given, and never invent a link.
Drop photo, home address, national ID, marital status, date of birth, gender, religion, parents' details and referee contact details — unless the source states they are required for the target country or application type.
If title is missing, derive it from the most recent job title.

SUMMARY
Three to four lines: professional level, field, strongest capabilities, what stands out in the experience or project history, and the value to an employer.
Write it in first person, active voice (Turkish 'ben dili': '...geliştiriyorum', never '...geliştirmiştir'). Never refer to the person in third person.
Avoid filler: motivated, hard-working, passionate, dynamic, seeking an opportunity, team player.

EXPERIENCE
Reverse chronological. Fill title, company, location, start_date and end_date.
Three to five bullets each, fewer for old or unrelated roles. Put every point in `bullets` and leave `description` empty.
Each bullet: strong verb + what was done + method or technology used + a verifiable result where the source has one. Never invent a number.
Strengthen weak phrasing without changing its meaning — "Responsible for database operations" becomes "Managed relational database operations and supported SQL-based data retrieval workflows".

PROJECTS
Fill name, kind, technologies and bullets. `kind` is academic, personal, freelance or professional, exactly as the source implies; never upgrade it.
Bullets cover the problem solved, the candidate's own technical work, the method or architecture used, and any result the source states.

SKILLS
Put every skill in exactly one skill_groups entry, and keep the flat `skills` list in sync with it.
Use three to five groups whose names fit THIS profession and are written in the target language. A developer gets groups like Programming Languages, Frameworks & Tools, Databases; a nurse, an accountant or a designer gets groups natural to their own field — never force technology categories onto them.
The group label key is "name", never "category".
Do not mix programming languages with tools, databases with frameworks, or soft skills with technical skills. Do not list the same skill in two groups.

SOFT SKILLS
Include communication, teamwork or leadership only if the source CV states them, and prefer evidencing them inside an experience or achievement bullet over listing them.

EDUCATION
Reverse chronological. Fill degree, school, location, start_date and year (graduation, or expected graduation).
Put GPA, scholarship, honours, relevant academic achievement and thesis into `details` when the source has them and they help.
Drop high school for experienced candidates; keep it for students and new graduates when it is all they have.

CERTIFICATIONS
Fill name, issuer and date. Never invent an issuer or a date.

DATES
One consistent format throughout. English: "Jan 2024 - Mar 2025", "Sep 2022 - Present", "Expected Jun 2027". Turkish: "Oca 2024 - Mar 2025", "Eyl 2022 - Devam Ediyor", "Beklenen Mezuniyet: Haz 2027".
Never guess a day or month the source does not give.

LENGTH
A student or new graduate is worth about one page of content; early career one to two; an experienced candidate at most two. Keep every important fact and cut repetition and padding."""


_VERIFICATION = (
    "verification_required: unclear, missing or contradictory information, fields "
    "you could not read, and the questions worth asking the candidate. One short "
    "sentence per entry; an empty list when there is nothing to confirm."
)


def build_rewrite_system(language: str) -> str:
    """System prompt for /ats/rewrite — no posting, no form."""
    return (
        f"{ATS_RULES}\n\n"
        "OUTPUT\n"
        'Respond ONLY with JSON: {"cv": <the CV in the schema you received>, '
        '"verification_required": [str], "optimization_summary": [str]}.\n'
        f"{_VERIFICATION}\n"
        "optimization_summary: what you restructured and what you removed. One "
        "short sentence per entry.\n"
        f"Answer in language: {language}."
    )


def build_apply_system(language: str) -> str:
    """System prompt for /apply/prepare — the same rules, plus the posting."""
    return (
        f"{ATS_RULES}\n\n"
        "POSTING\n"
        "You are tailoring this CV to one specific job application and answering its form.\n"
        "Input JSON: cv, job_text, form (fields with id/label/type/options).\n"
        "Read the posting's role name, responsibilities, technical requirements and "
        "keywords. Identify what the CV genuinely matches, move the most relevant "
        "experience, projects and skills forward, and use supported keywords "
        "naturally. Never add a skill the candidate lacks, never claim a job title "
        "their history does not support, never keyword-stuff, and keep the text "
        "readable by a human.\n\n"
        "OUTPUT\n"
        'Respond ONLY with JSON: {"cv": <the tailored CV, same schema>, '
        '"changes": [str], "verification_required": [str], "cover_letter": str, '
        '"answers": [{"field_id": str, "value": str}], '
        '"company": str|null, "title": str|null}.\n'
        "company/title: the hiring organization and the role, exactly as the posting "
        "names them; null if it does not say.\n"
        "changes: a short user-facing list of what you altered, including anything "
        "the posting asked for that the CV does not support and you therefore did "
        "not add.\n"
        f"{_VERIFICATION}\n"
        "cover_letter: always write one, first person, active voice, grounded in the "
        "CV and the posting.\n"
        "answers: one per form field except type=file. Identity fields "
        "(name/email/phone/location, and the LinkedIn/GitHub/portfolio URLs from "
        "cv.linkedin/cv.github/cv.website) come from the CV. For select/radio pick "
        "EXACTLY one option verbatim from options. If the CV lacks the information, "
        'use value "" so the user fills it.\n'
        f"Answer in language: {language}."
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\api && .venv\Scripts\python -m pytest tests/test_ats_prompt.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add api/app/services/ats_prompt.py api/tests/test_ats_prompt.py
git commit -m "feat(api): one ATS rule set for both the rewrite and the assisted apply"
```

---

### Task 3: Wire /ats/rewrite to the new prompt and response

**Files:**
- Modify: `api/app/services/ats.py:1-52` (replace `SYSTEM` and `rewrite_ats`)
- Modify: `api/app/routers/ats.py:18-24`
- Test: `api/tests/test_ats.py`

**Interfaces:**
- Consumes: `build_rewrite_system(language)` from Task 2.
- Produces: `RewriteOut(cv: CVData, verification_required: list[str], optimization_summary: list[str])` in `app/services/ats.py`; `rewrite_ats(cv, language, llm) -> RewriteOut`.

- [ ] **Step 1: Write the failing tests**

Append to `api/tests/test_ats.py`:

```python
def test_rewrite_endpoint_returns_verification_and_summary(client, auth_headers):
    payload = {
        "cv": json.loads(SAMPLE_CV_JSON),
        "verification_required": ["Confirm the end date of the Developer role."],
        "optimization_summary": ["Grouped skills by category."],
    }
    override_llm([json.dumps(payload)])
    r = client.post("/ats/rewrite", headers=auth_headers,
                    json={"cv": json.loads(SAMPLE_CV_JSON), "language": "en"})
    assert r.status_code == 200
    body = r.json()
    assert body["cv"]["full_name"] == "Ada Lovelace"
    assert body["verification_required"] == ["Confirm the end date of the Developer role."]
    assert body["optimization_summary"] == ["Grouped skills by category."]


def test_rewrite_endpoint_defaults_the_lists_to_empty(client, auth_headers):
    override_llm([json.dumps({"cv": json.loads(SAMPLE_CV_JSON)})])
    r = client.post("/ats/rewrite", headers=auth_headers,
                    json={"cv": json.loads(SAMPLE_CV_JSON), "language": "en"})
    assert r.status_code == 200
    assert r.json()["verification_required"] == []
    assert r.json()["optimization_summary"] == []


def test_rewrite_sends_the_shared_rules(client, auth_headers):
    from app.services.ats_prompt import ATS_RULES

    fake = override_llm([json.dumps({"cv": json.loads(SAMPLE_CV_JSON)})])
    client.post("/ats/rewrite", headers=auth_headers,
                json={"cv": json.loads(SAMPLE_CV_JSON), "language": "tr"})
    system = fake.calls[0]["messages"][0]["content"]
    assert ATS_RULES in system
    assert "Answer in language: tr." in system
```

The three pre-existing rewrite tests (`test_rewrite_endpoint`, `test_rewrite_endpoint_returns_skill_groups`, `test_rewrite_endpoint_accepts_category_alias`) now queue a bare CV where the model must return a wrapper. Update each of them to wrap its payload:

```python
def test_rewrite_endpoint(client, auth_headers):
    override_llm([json.dumps({"cv": json.loads(SAMPLE_CV_JSON)})])
    r = client.post("/ats/rewrite", headers=auth_headers,
                    json={"cv": json.loads(SAMPLE_CV_JSON), "language": "en"})
    assert r.status_code == 200
    assert r.json()["cv"]["full_name"] == "Ada Lovelace"


def test_rewrite_endpoint_returns_skill_groups(client, auth_headers):
    rewritten = json.loads(SAMPLE_CV_JSON)
    rewritten["skill_groups"] = [{"name": "Programming Languages", "skills": ["Python"]}]
    override_llm([json.dumps({"cv": rewritten})])
    r = client.post("/ats/rewrite", headers=auth_headers,
                    json={"cv": json.loads(SAMPLE_CV_JSON), "language": "en"})
    assert r.status_code == 200
    assert r.json()["cv"]["skill_groups"][0]["name"] == "Programming Languages"


def test_rewrite_endpoint_accepts_category_alias(client, auth_headers):
    # Gemini labels groups "category" despite the prompt; must not 502
    rewritten = json.loads(SAMPLE_CV_JSON)
    rewritten["skill_groups"] = [{"category": "Programlama Dilleri", "skills": ["Python", "C"]}]
    override_llm([json.dumps({"cv": rewritten})])
    r = client.post("/ats/rewrite", headers=auth_headers,
                    json={"cv": json.loads(SAMPLE_CV_JSON), "language": "tr"})
    assert r.status_code == 200
    assert r.json()["cv"]["skill_groups"][0]["name"] == "Programlama Dilleri"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\api && .venv\Scripts\python -m pytest tests/test_ats.py -v`
Expected: FAIL — the endpoint returns `{"cv": ...}` only, and `rewrite_ats` validates the model output against `CVData`, which rejects the wrapper.

- [ ] **Step 3: Write the implementation**

In `api/app/services/ats.py`, delete the `SYSTEM` constant (lines 8-27) and replace `rewrite_ats`:

```python
from pathlib import Path

from fpdf import FPDF
from pydantic import BaseModel

from app.schemas import CVData
from app.services.ats_prompt import build_rewrite_system
from app.services.llm import MODEL_SMART, LLMClient


class RewriteOut(BaseModel):
    cv: CVData
    # What the model could not confirm from the source, and what it changed.
    # Neither reaches the PDF; both are shown next to the result.
    verification_required: list[str] = []
    optimization_summary: list[str] = []


def rewrite_ats(cv: CVData, language: str, llm: LLMClient) -> RewriteOut:
    return llm.chat_json(MODEL_SMART, build_rewrite_system(language),
                         cv.model_dump_json(), RewriteOut)
```

In `api/app/routers/ats.py`, return the whole object instead of wrapping it:

```python
@router.post("/rewrite")
def rewrite(
    req: AtsRequest,
    user_id: str = Depends(check_usage),
    llm: LLMClient = Depends(get_llm),
):
    return rewrite_ats(req.cv, req.language, llm)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\api && .venv\Scripts\python -m pytest tests/test_ats.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/services/ats.py api/app/routers/ats.py api/tests/test_ats.py
git commit -m "feat(api): return verification notes and an edit summary from the ATS rewrite"
```

---

### Task 4: Wire /apply/prepare to the shared rules

**Files:**
- Modify: `api/app/services/apply.py:30-59` (drop `SYSTEM`, extend `PrepareOut`), `api/app/services/apply.py:170`
- Test: `api/tests/test_apply_prepare.py`

**Interfaces:**
- Consumes: `build_apply_system(language)` from Task 2.
- Produces: `PrepareOut.verification_required: list[str]`.

- [ ] **Step 1: Write the failing tests**

Append to `api/tests/test_apply_prepare.py`. It already defines `_use_driver`, `_html` and `PREPARE_OUT` (line 21) and posts its request body inline, so these follow the same shape:

```python
def test_prepare_returns_verification_required(client, auth_headers):
    _use_driver(FakeDriver([_html("greenhouse_like.html")]))
    out = json.loads(PREPARE_OUT)
    out["verification_required"] = ["Confirm whether the Acme role was an internship."]
    override_llm([json.dumps(out)])
    r = client.post("/apply/prepare", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://jobs.example.com/1",
        "language": "en",
    })
    assert r.status_code == 200
    assert r.json()["verification_required"] == [
        "Confirm whether the Acme role was an internship."
    ]


def test_prepare_defaults_verification_required_to_empty(client, auth_headers):
    _use_driver(FakeDriver([_html("greenhouse_like.html")]))
    override_llm([PREPARE_OUT])
    r = client.post("/apply/prepare", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://jobs.example.com/1",
        "language": "en",
    })
    assert r.status_code == 200
    assert r.json()["verification_required"] == []


def test_prepare_sends_the_shared_rules(client, auth_headers):
    from app.services.ats_prompt import ATS_RULES

    _use_driver(FakeDriver([_html("greenhouse_like.html")]))
    fake = override_llm([PREPARE_OUT])
    client.post("/apply/prepare", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://jobs.example.com/1",
        "language": "tr",
    })
    system = fake.calls[0]["messages"][0]["content"]
    assert ATS_RULES in system
    assert "job_text" in system
    assert "Answer in language: tr." in system
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\api && .venv\Scripts\python -m pytest tests/test_apply_prepare.py -v`
Expected: FAIL — `verification_required` is not a field on `PrepareOut`, so the response has no such key.

- [ ] **Step 3: Write the implementation**

In `api/app/services/apply.py`, delete the `SYSTEM` constant (lines 30-48), import the builder, and add the field:

```python
from app.services.ats_prompt import build_apply_system


class PrepareOut(BaseModel):
    cv: CVData
    changes: list[str] = []
    # What the model could not confirm from the CV. Shown on the approval screen
    # so the user fixes it before the application goes out, not after.
    verification_required: list[str] = []
    cover_letter: str | None = None
    answers: list[FieldAnswer] = []
    # Read off the posting the model was already given, so the saved
    # application can name itself instead of landing in the list as "unknown".
    company: str | None = None
    title: str | None = None
```

At line 170, swap the prompt:

```python
        out = llm.chat_json(MODEL_SMART, build_apply_system(language),
```

Leave `ASSIST_SYSTEM` and its call at line 294 untouched: that flow fills a form page and never rewrites the CV, so the ATS rules do not apply to it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\api && .venv\Scripts\python -m pytest tests/test_apply_prepare.py tests/test_apply_assist.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/services/apply.py api/tests/test_apply_prepare.py
git commit -m "feat(api): hold the assisted apply to the same ATS rules"
```

---

### Task 5: Teach the parser to see projects and achievements

**Files:**
- Modify: `api/app/services/cv_parser.py:4-19`
- Test: `api/tests/test_cv_parse.py`

**Interfaces:**
- Consumes: the Task 1 schema.
- Produces: nothing new — `parse_cv(text, llm) -> CVData` keeps its signature.

- [ ] **Step 1: Write the failing tests**

Append to `api/tests/test_cv_parse.py`:

```python
def test_parser_prompt_asks_for_the_new_sections():
    from app.services.cv_parser import SYSTEM

    for field in ("projects", "achievements", "bullets", "issuer", "details"):
        assert field in SYSTEM


def test_parse_returns_projects_and_structured_certifications(client, auth_headers,
                                                              sample_pdf_bytes):
    parsed = json.loads(SAMPLE_CV_JSON)
    parsed["projects"] = [{"name": "Bombe", "kind": "academic",
                           "technologies": ["Python"], "bullets": ["Cracked ciphers."]}]
    parsed["achievements"] = ["Best paper award, 1843"]
    parsed["certifications"] = [{"name": "AWS SAA", "issuer": "Amazon", "date": "Mar 2024"}]
    override_llm([json.dumps(parsed)])
    r = client.post("/cv/parse", headers=auth_headers,
                    files={"file": ("cv.pdf", sample_pdf_bytes, "application/pdf")})
    assert r.status_code == 200
    body = r.json()
    assert body["projects"][0]["kind"] == "academic"
    assert body["achievements"] == ["Best paper award, 1843"]
    assert body["certifications"][0]["issuer"] == "Amazon"
```

This matches the call shape the file already uses (`test_cv_parse.py:8`), including the `sample_pdf_bytes` fixture from `conftest.py`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\api && .venv\Scripts\python -m pytest tests/test_cv_parse.py -v`
Expected: FAIL on the prompt assertion — `"projects" not in SYSTEM`.

- [ ] **Step 3: Write the implementation**

Replace the schema fragment in `api/app/services/cv_parser.py`:

```python
SYSTEM = (
    "You are a CV parser. Extract structured data from the CV text. "
    "Respond ONLY with JSON matching this schema: "
    '{"full_name": str, "title": str|null, "email": str|null, "phone": str|null, '
    '"location": str|null, "linkedin": str|null, "github": str|null, '
    '"website": str|null, "summary": str|null, '
    '"experiences": [{"title": str, "company": str, "location": str|null, '
    '"start_date": str|null, "end_date": str|null, "description": str|null, '
    '"bullets": [str]}], '
    '"education": [{"degree": str|null, "school": str, "location": str|null, '
    '"start_date": str|null, "year": str|null, "details": [str]}], '
    '"projects": [{"name": str, "kind": str|null, "technologies": [str], '
    '"bullets": [str]}], '
    '"skills": [str], "achievements": [str], "languages": [str], '
    '"certifications": [{"name": str, "issuer": str|null, "date": str|null}]}. '
    '"title" is the professional headline shown under the name, if any. '
    "linkedin/github/website are the person's profile URLs wherever they appear "
    "(header, contact block, or a hyperlink); keep them as full URLs. "
    '"website" is a personal site or portfolio. '
    "experiences[].bullets: one entry per bullet the CV lists under that role; "
    "leave it empty and use description when the CV writes a paragraph instead. "
    'projects[].kind: "academic", "personal", "freelance" or "professional", only '
    "when the CV makes it clear; null otherwise. Never upgrade a project's kind. "
    "education[].details: GPA, honours, scholarship or thesis, when stated. "
    "achievements: awards, competitions, volunteering and activities that are not "
    "jobs, projects or certificates. "
    "Keep the CV's original language. Do not invent information."
)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\api && .venv\Scripts\python -m pytest tests/test_cv_parse.py -v`
Expected: PASS, and every pre-existing test in the file still passes — the prompt gained fields but changed none of the old ones.

- [ ] **Step 5: Commit**

```bash
git add api/app/services/cv_parser.py api/tests/test_cv_parse.py
git commit -m "feat(api): extract projects, achievements and certificate issuers when parsing a CV"
```

---

### Task 6: Render the new sections and layout

**Files:**
- Modify: `api/app/services/ats.py:29-34` (`HEADINGS`) and the `render_pdf` body
- Test: `api/tests/test_ats.py`

**Interfaces:**
- Consumes: the Task 1 schema.
- Produces: nothing new — `render_pdf(cv, language) -> bytes` keeps its signature.

- [ ] **Step 1: Write the failing tests**

Append to `api/tests/test_ats.py`:

```python
def test_render_pdf_uses_bullets_when_present():
    import pymupdf

    from app.schemas import Experience

    cv = _cv()
    cv.experiences = [Experience(title="Developer", company="Acme",
                                 location="İstanbul, Türkiye",
                                 start_date="Oca 2024", end_date="Devam Ediyor",
                                 bullets=["Designed REST APIs.", "Tuned SQL queries."])]
    text = pymupdf.open(stream=render_pdf(cv, "tr"), filetype="pdf")[0].get_text()
    assert "Designed REST APIs." in text
    assert "Tuned SQL queries." in text
    assert "İstanbul, Türkiye" in text


def test_render_pdf_falls_back_to_description():
    import pymupdf

    cv = _cv()  # SAMPLE_CV_JSON has description, no bullets
    text = pymupdf.open(stream=render_pdf(cv, "en"), filetype="pdf")[0].get_text()
    assert "Built compute engines." in text


def test_render_pdf_includes_projects_and_achievements():
    import pymupdf

    from app.schemas import Project

    cv = _cv()
    cv.projects = [Project(name="Bombe", kind="academic", technologies=["Python", "C"],
                           bullets=["Cracked ciphers."])]
    cv.achievements = ["Best paper award, 1843"]
    text = pymupdf.open(stream=render_pdf(cv, "en"), filetype="pdf")[0].get_text()
    assert "PROJECTS" in text
    assert "Bombe" in text and "academic" in text
    assert "Python, C" in text
    assert "ACHIEVEMENTS" in text
    assert "Best paper award, 1843" in text


def test_render_pdf_structured_certifications():
    import pymupdf

    from app.schemas import Certification

    cv = _cv()
    cv.certifications = [Certification(name="AWS SAA", issuer="Amazon", date="Mar 2024"),
                         Certification(name="Scrum Master")]
    text = pymupdf.open(stream=render_pdf(cv, "en"), filetype="pdf")[0].get_text()
    assert "AWS SAA | Amazon | Mar 2024" in text
    assert "Scrum Master" in text
    assert "None" not in text


def test_render_pdf_contact_block_is_split():
    import pymupdf

    cv = _cv()
    cv.linkedin = "linkedin.com/in/ada"
    cv.github = "github.com/ada"
    lines = pymupdf.open(stream=render_pdf(cv, "en"), filetype="pdf")[0].get_text().splitlines()
    contact = next(line for line in lines if "ada@example.com" in line)
    links = next(line for line in lines if "linkedin.com/in/ada" in line)
    assert contact != links          # the two blocks are on separate lines
    assert "linkedin" not in contact


def test_render_pdf_skills_heading_is_not_technical():
    import pymupdf

    text = pymupdf.open(stream=render_pdf(_cv(), "tr"), filetype="pdf")[0].get_text()
    assert "BECERİLER" in text
    assert "TEKNİK BECERİLER" not in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\api && .venv\Scripts\python -m pytest tests/test_ats.py -v`
Expected: FAIL — no projects section, no achievements section, contact still on one line, certifications rendered via `join` on model objects.

- [ ] **Step 3: Write the implementation**

Replace `HEADINGS` in `api/app/services/ats.py`:

```python
HEADINGS = {
    "tr": {"summary": "PROFESYONEL ÖZET", "skills": "BECERİLER",
           "experience": "İŞ DENEYİMİ", "projects": "PROJELER",
           "education": "EĞİTİM", "certifications": "SERTİFİKALAR",
           "achievements": "BAŞARILAR VE AKTİVİTELER", "languages": "YABANCI DİLLER"},
    "en": {"summary": "PROFESSIONAL SUMMARY", "skills": "SKILLS",
           "experience": "EXPERIENCE", "projects": "PROJECTS",
           "education": "EDUCATION", "certifications": "CERTIFICATIONS",
           "achievements": "ACHIEVEMENTS", "languages": "LANGUAGES"},
}
```

The skills heading stays "BECERİLER"/"SKILLS" rather than "TEKNİK BECERİLER": group names already adapt to the profession, and a hard "Technical Skills" heading would be wrong on a nurse's or an accountant's CV.

Replace the body of `render_pdf` from the header down. Section order is fixed — Summary, Skills, Experience, Projects, Education, Certifications, Achievements, Languages — and empty sections are skipped, which is what puts Education and Projects near the top for a candidate with no experience:

```python
def render_pdf(cv: CVData, language: str) -> bytes:
    h = HEADINGS.get(language, HEADINGS["en"])
    regular, bold = _find_fonts()
    pdf = FPDF()
    pdf.add_font("Main", "", regular)
    pdf.add_font("Main", "B", bold)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def heading(text: str):
        # Left-aligned section break over a full-width rule
        pdf.ln(1)
        pdf.set_font("Main", "B", 12)
        pdf.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(120, 120, 120)
        pdf.set_line_width(0.3)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(2)
        pdf.set_font("Main", "", 10.5)

    def line(text: str):
        # fpdf2 2.8.x leaves the cursor at line end; reset to the left margin
        pdf.multi_cell(0, 5.5, text, new_x="LMARGIN", new_y="NEXT")

    def bullet(text: str):
        pdf.set_x(pdf.l_margin + 4)
        pdf.multi_cell(0, 5.5, f"• {text}", new_x="LMARGIN", new_y="NEXT")

    def bold_line(text: str):
        pdf.set_font("Main", "B", 10.5)
        line(text)
        pdf.set_font("Main", "", 10.5)

    def dates(start: str | None, end: str | None) -> str:
        return " - ".join(x for x in (start, end) if x)

    pdf.set_font("Main", "B", 19)
    pdf.cell(0, 11, cv.full_name, new_x="LMARGIN", new_y="NEXT")
    if cv.title:
        pdf.set_font("Main", "", 12)
        pdf.cell(0, 7, cv.title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Main", "", 10)
    # Two blocks, two lines: long profile URLs stop competing with the phone
    # number for one line, and both stay plain text for the parser.
    for block in ([cv.location, cv.phone, cv.email],
                  [cv.linkedin, cv.github, cv.website]):
        text = " | ".join(x for x in block if x)
        if text:
            pdf.cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    if cv.summary:
        heading(h["summary"]); line(cv.summary); pdf.ln(2)

    if cv.skill_groups or cv.skills:
        heading(h["skills"])
        if cv.skill_groups:
            for g in cv.skill_groups:
                if not g.skills:
                    continue
                pdf.set_font("Main", "B", 10.5)
                pdf.write(5.5, f"{g.name}: ")
                pdf.set_font("Main", "", 10.5)
                pdf.write(5.5, ", ".join(g.skills))
                pdf.ln(6.5)
        else:
            line(", ".join(cv.skills))
        pdf.ln(2)

    if cv.experiences:
        heading(h["experience"])
        for e in cv.experiences:
            bold_line(e.title)
            line(" | ".join(x for x in (e.company, e.location) if x))
            span = dates(e.start_date, e.end_date)
            if span:
                line(span)
            for b in e.bullets:
                bullet(b)
            if not e.bullets and e.description:
                line(e.description)
            pdf.ln(1)
        pdf.ln(1)

    if cv.projects:
        heading(h["projects"])
        for p in cv.projects:
            bold_line(" | ".join(x for x in (p.name, p.kind) if x))
            if p.technologies:
                line(", ".join(p.technologies))
            for b in p.bullets:
                bullet(b)
            pdf.ln(1)
        pdf.ln(1)

    if cv.education:
        heading(h["education"])
        for ed in cv.education:
            bold_line(ed.degree or ed.school)
            if ed.degree:
                line(" | ".join(x for x in (ed.school, ed.location) if x))
            elif ed.location:
                line(ed.location)
            span = dates(ed.start_date, ed.year)
            if span:
                line(span)
            for d in ed.details:
                bullet(d)
            pdf.ln(1)
        pdf.ln(1)

    if cv.certifications:
        heading(h["certifications"])
        for c in cv.certifications:
            line(" | ".join(x for x in (c.name, c.issuer, c.date) if x))
        pdf.ln(2)

    if cv.achievements:
        heading(h["achievements"])
        for a in cv.achievements:
            bullet(a)
        pdf.ln(2)

    if cv.languages:
        heading(h["languages"]); line(", ".join(cv.languages))

    return bytes(pdf.output())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\api && .venv\Scripts\python -m pytest tests/test_ats.py -v`
Expected: PASS. `test_render_pdf_title_and_header_text`, `test_render_pdf_includes_profile_links`, `test_render_pdf_education_without_degree` and `test_render_pdf_grouped_skills` still pass unchanged — they assert on text content, not alignment.

- [ ] **Step 5: Run the whole API suite**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\api && .venv\Scripts\python -m pytest -q`
Expected: PASS, all tests.

- [ ] **Step 6: Commit**

```bash
git add api/app/services/ats.py api/tests/test_ats.py
git commit -m "feat(api): render projects, achievements and bullet experience in the ATS PDF"
```

---

### Task 7: Mirror the schema in the web types and API client

**Files:**
- Modify: `web/src/types/api.ts:3-40`, `web/src/types/api.ts:81-91`
- Modify: `web/src/lib/api.ts:65-74`

**Interfaces:**
- Consumes: the Task 1 and Task 3 shapes.
- Produces: `Project`, `Certification`, `AtsRewriteResult` types; `atsRewrite(cv, language) -> Promise<AtsRewriteResult>`.

- [ ] **Step 1: Write the failing test**

Append to the existing `web/src/lib/__tests__/api.test.ts`. It already mocks `@/lib/supabase/client`, defines `jsonResponse(status, body)` and a `CV` constant, and sets `global.fetch = vi.fn()` in `beforeEach` — reuse all four. Add `atsRewrite` to the file's existing import from `@/lib/api`:

```ts
it('atsRewrite returns the cv together with both note lists', async () => {
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(200, {
    cv: CV,
    verification_required: ['Confirm the end date.'],
    optimization_summary: ['Grouped skills.'],
  }))
  const result = await atsRewrite(CV, 'en')
  expect(result.cv.full_name).toBe('Ada')
  expect(result.verification_required).toEqual(['Confirm the end date.'])
  expect(result.optimization_summary).toEqual(['Grouped skills.'])
  const [url] = (global.fetch as Mock).mock.calls[0]
  expect(String(url)).toBe('http://localhost:8000/ats/rewrite')
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\web && npm test -- api.atsRewrite`
Expected: FAIL — `atsRewrite` resolves to the CV object, so `result.cv` is `undefined`.

- [ ] **Step 3: Write the implementation**

In `web/src/types/api.ts`:

```ts
export interface Experience {
  title: string
  company: string
  location?: string | null
  start_date: string | null
  end_date: string | null
  /** Legacy paragraph form; rows written before the ATS engine use this. */
  description: string | null
  /** Set by the ATS rewrite; absent on older rows. */
  bullets?: string[]
}

export interface Education {
  degree: string | null
  school: string
  location?: string | null
  start_date?: string | null
  year: string | null
  details?: string[]
}

export interface Project {
  name: string
  kind: string | null
  technologies: string[]
  bullets: string[]
}

export interface Certification {
  name: string
  issuer: string | null
  date: string | null
}
```

In `CVData`, replace the `certifications` line and add the two new fields:

```ts
  /** Absent on older rows. */
  projects?: Project[]
  achievements?: string[]
  languages: string[]
  /**
   * The API coerces plain strings into Certification objects, but rows read
   * straight out of Supabase were written before that existed and still hold
   * strings. Every consumer must handle both.
   */
  certifications: (Certification | string)[]
```

Add the rewrite result type next to `CVData`:

```ts
export interface AtsRewriteResult {
  cv: CVData
  verification_required: string[]
  optimization_summary: string[]
}
```

Add the field to `OptimizedPayload`, next to `changes`:

```ts
  changes: string[]
  verification_required?: string[]
```

In `web/src/lib/api.ts`, import `AtsRewriteResult` and return the whole body:

```ts
export async function atsRewrite(cv: CVData, language: string): Promise<AtsRewriteResult> {
  const res = await ensureOk(
    await fetch(apiUrl('/ats/rewrite'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ cv, language }),
    })
  )
  return res.json()
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\web && npm test -- api.atsRewrite`
Expected: PASS.

- [ ] **Step 5: Check types**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\web && npx tsc --noEmit`
Expected: errors in `ats/page.tsx` (uses the old return shape) and `cv/[id]/page.tsx` (joins certifications). Tasks 8 and 10 fix them; do not fix them here.

- [ ] **Step 6: Commit**

```bash
git add web/src/types/api.ts web/src/lib/api.ts web/src/lib/__tests__/api.atsRewrite.test.ts
git commit -m "feat(web): mirror the extended CV schema and the ATS rewrite result"
```

---

### Task 8: Show the two note panels on the ATS page

**Files:**
- Modify: `web/src/app/(app)/ats/page.tsx:47-76`, `:122-139`
- Modify: `web/src/messages/tr.json`, `web/src/messages/en.json` (the `ats` namespace)
- Test: `web/src/app/(app)/ats/__tests__/page.test.tsx`

**Interfaces:**
- Consumes: `AtsRewriteResult` from Task 7.
- Produces: nothing other tasks depend on.

- [ ] **Step 1: Write the failing test**

Append to `web/src/app/(app)/ats/__tests__/page.test.tsx`. The file renders with `renderWithIntl(<AtsPage />)` and clicks the button by its Turkish label (line 74); match that exactly:

```tsx
it('shows the verification and edit-summary panels after converting', async () => {
  ;(atsRewrite as Mock).mockResolvedValue({
    cv: CVS[0].parsed_data,
    verification_required: ['Confirm the end date of the Developer role.'],
    optimization_summary: ['Grouped skills by category.'],
  })
  ;(atsPdf as Mock).mockResolvedValue(new Blob(['%PDF'], { type: 'application/pdf' }))
  renderWithIntl(<AtsPage />)
  await screen.findByLabelText('CV')
  await userEvent.click(screen.getByRole('button', { name: "ATS'ye Çevir" }))
  expect(await screen.findByText('Confirm the end date of the Developer role.')).toBeInTheDocument()
  expect(screen.getByText('Grouped skills by category.')).toBeInTheDocument()
})

it('shows no panels when both lists are empty', async () => {
  ;(atsRewrite as Mock).mockResolvedValue({
    cv: CVS[0].parsed_data, verification_required: [], optimization_summary: [],
  })
  ;(atsPdf as Mock).mockResolvedValue(new Blob(['%PDF'], { type: 'application/pdf' }))
  renderWithIntl(<AtsPage />)
  await screen.findByLabelText('CV')
  await userEvent.click(screen.getByRole('button', { name: "ATS'ye Çevir" }))
  expect(await screen.findByText(/Dönüştürüldü/)).toBeInTheDocument()
  expect(screen.queryByTestId('ats-verification')).not.toBeInTheDocument()
  expect(screen.queryByTestId('ats-summary')).not.toBeInTheDocument()
})
```

The existing `converts, downloads the PDF and saves the ATS copy` test (line 69) mocks `atsRewrite` with a bare CV. Change that one line to the wrapper shape, or the page will read `.cv` off a CV object and save `undefined`:

```tsx
  ;(atsRewrite as Mock).mockResolvedValue({
    cv: CVS[0].parsed_data, verification_required: [], optimization_summary: [],
  })
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\web && npm test -- ats/__tests__/page`
Expected: FAIL — the panels do not render.

- [ ] **Step 3: Write the implementation**

Add the messages. `web/src/messages/tr.json`, inside `ats`:

```json
    "verification": "Doğrulaman gerekenler",
    "verificationIntro": "Bu bilgileri CV'ye eklemedik çünkü kaynakta net değildi. Doğruysa kendin ekle.",
    "summary": "Yapılan düzenlemeler"
```

`web/src/messages/en.json`, inside `ats`:

```json
    "verification": "Worth confirming",
    "verificationIntro": "We left these out because the source CV was not clear. Add them yourself if they are right.",
    "summary": "What we changed"
```

In `web/src/app/(app)/ats/page.tsx`, hold the notes in state and read `.cv` from the result:

```tsx
  const [notes, setNotes] = useState<{ verification: string[]; summary: string[] }>(
    { verification: [], summary: [] }
  )
```

Inside `convert()`, replace the first two lines of the `try` block:

```tsx
      const result = await atsRewrite(cv.parsed_data, atsLang)
      const rewritten = result.cv
      setNotes({
        verification: result.verification_required ?? [],
        summary: result.optimization_summary ?? [],
      })
      const pdf = await atsPdf(rewritten, atsLang)
```

Reset the notes wherever `setDone(false)` already runs — at the top of `convert()` and in the `CvSelect` `onChange` handler:

```tsx
      setNotes({ verification: [], summary: [] })
```

Render the panels directly after the `done` block (before `{busy && <ProgressBar .../>}`):

```tsx
          {notes.verification.length > 0 && (
            <div data-testid="ats-verification" className="rounded-lg bg-secondary/60 px-4 py-3">
              <p className="type-ui font-medium text-foreground">{t('ats.verification')}</p>
              <p className="type-ui mt-0.5 text-muted-foreground">{t('ats.verificationIntro')}</p>
              <ul className="type-ui mt-2 list-disc pl-5 text-muted-foreground">
                {notes.verification.map((v, i) => <li key={i}>{v}</li>)}
              </ul>
            </div>
          )}
          {notes.summary.length > 0 && (
            <div data-testid="ats-summary" className="rounded-lg bg-secondary/60 px-4 py-3">
              <p className="type-ui font-medium text-foreground">{t('ats.summary')}</p>
              <ul className="type-ui mt-2 list-disc pl-5 text-muted-foreground">
                {notes.summary.map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </div>
          )}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\web && npm test -- ats/__tests__/page`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/app/\(app\)/ats/page.tsx web/src/app/\(app\)/ats/__tests__/page.test.tsx web/src/messages/tr.json web/src/messages/en.json
git commit -m "feat(web): show what the ATS rewrite changed and what needs confirming"
```

---

### Task 9: Show the verification list on the approval screen

**Files:**
- Modify: `web/src/components/apply/ApprovalScreen.tsx:34-41`
- Modify: `web/src/messages/tr.json`, `web/src/messages/en.json` (the `optimize` namespace)
- Test: `web/src/components/apply/__tests__/ApprovalScreen.test.tsx`

**Interfaces:**
- Consumes: `OptimizedPayload.verification_required` from Task 7.
- Produces: nothing other tasks depend on.

- [ ] **Step 1: Write the failing test**

Append to `web/src/components/apply/__tests__/ApprovalScreen.test.tsx`, reusing its `PAYLOAD` fixture and `renderWithIntl` helper:

```tsx
it('lists what the model could not confirm', () => {
  renderWithIntl(<ApprovalScreen
    payload={{ ...PAYLOAD, verification_required: ['Confirm the Acme role was not an internship.'] }}
    canSubmit onSubmit={vi.fn()} onDeliver={vi.fn()} />)
  expect(screen.getByText('Confirm the Acme role was not an internship.')).toBeInTheDocument()
})

it('omits the verification block when there is nothing to confirm', () => {
  renderWithIntl(<ApprovalScreen payload={PAYLOAD} canSubmit onSubmit={vi.fn()} onDeliver={vi.fn()} />)
  expect(screen.queryByTestId('approval-verification')).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\web && npm test -- ApprovalScreen`
Expected: FAIL — the text is not rendered.

- [ ] **Step 3: Write the implementation**

Add to the `optimize` namespace in both message files:

```json
    "verification": "Doğrulaman gerekenler"
```

```json
    "verification": "Worth confirming"
```

In `ApprovalScreen.tsx`, after the existing `changes` block and inside the same `<section>`:

```tsx
        {(payload.verification_required?.length ?? 0) > 0 && (
          <div data-testid="approval-verification">
            <p className="mb-1 text-sm font-medium text-foreground">{t('verification')}</p>
            <ul className="list-disc pl-5 text-sm text-muted-foreground">
              {payload.verification_required!.map((v, i) => <li key={i}>{v}</li>)}
            </ul>
          </div>
        )}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\web && npm test -- ApprovalScreen`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/apply/ApprovalScreen.tsx web/src/components/apply/__tests__/ApprovalScreen.test.tsx web/src/messages/tr.json web/src/messages/en.json
git commit -m "feat(web): surface unconfirmed CV facts before an application goes out"
```

---

### Task 10: Render projects, achievements and certificates on the CV page

**Files:**
- Modify: `web/src/app/(app)/cv/[id]/page.tsx:66-145`
- Modify: `web/src/messages/tr.json`, `web/src/messages/en.json` (the `cv` namespace)
- Modify: `web/src/app/(app)/cv/[id]/__tests__/page.test.tsx`

**Interfaces:**
- Consumes: the Task 7 types.
- Produces: nothing.

- [ ] **Step 1: Write the failing test**

The existing test file mocks `getCv` with a fixed `ROW` (line 27). Make it re-targetable and add three tests. Change the mock and add the import:

```tsx
import { getCv } from '@/lib/db'
import type { CVData } from '@/types/api'

vi.mock('@/lib/db', () => ({
  getCv: vi.fn(async () => ROW),
}))

function withParsedData(data: Partial<CVData>) {
  vi.mocked(getCv).mockResolvedValue({
    ...ROW, parsed_data: { ...ROW.parsed_data, ...data },
  })
}
```

Then append:

```tsx
it('renders projects, achievements and structured certifications', async () => {
  withParsedData({
    projects: [{ name: 'Bombe', kind: 'academic', technologies: ['Python'],
                 bullets: ['Cracked ciphers.'] }],
    achievements: ['Best paper award, 1843'],
    certifications: [{ name: 'AWS SAA', issuer: 'Amazon', date: 'Mar 2024' }],
  })
  renderWithIntl(<CvDetailPage />)
  expect(await screen.findByText('Bombe')).toBeInTheDocument()
  expect(screen.getByText('Cracked ciphers.')).toBeInTheDocument()
  expect(screen.getByText('Best paper award, 1843')).toBeInTheDocument()
  expect(screen.getByText('AWS SAA | Amazon | Mar 2024')).toBeInTheDocument()
})

it('still renders certifications stored as plain strings', async () => {
  withParsedData({ certifications: ['AWS SAA', 'Scrum Master'] })
  renderWithIntl(<CvDetailPage />)
  expect(await screen.findByText('AWS SAA')).toBeInTheDocument()
  expect(screen.getByText('Scrum Master')).toBeInTheDocument()
})

it('renders experience bullets when present', async () => {
  withParsedData({
    experiences: [{ title: 'Developer', company: 'Acme', location: 'İstanbul',
                    start_date: 'Oca 2024', end_date: 'Devam Ediyor',
                    description: null, bullets: ['Designed REST APIs.'] }],
  })
  renderWithIntl(<CvDetailPage />)
  expect(await screen.findByText('Designed REST APIs.')).toBeInTheDocument()
})
```

The first test in the file (`renders the parsed CV preview`) must keep passing untouched — it relies on the default `ROW`, so reset the mock between tests if the suite does not already do so.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\web && npm test -- cv/`
Expected: FAIL — no projects section, and certifications render via `.join()` which produces `[object Object]`.

- [ ] **Step 3: Write the implementation**

Add to the `cv` namespace in both message files:

```json
    "projects": "Projeler",
    "achievements": "Başarılar ve Aktiviteler"
```

```json
    "projects": "Projects",
    "achievements": "Achievements"
```

In `web/src/app/(app)/cv/[id]/page.tsx`, add a label helper above the component:

```tsx
import type { Certification } from '@/types/api'

/** Rows written before the ATS engine store certifications as plain strings. */
function certLabel(c: Certification | string): string {
  return typeof c === 'string' ? c : [c.name, c.issuer, c.date].filter(Boolean).join(' | ')
}
```

Render bullets inside the experience list item, replacing the `e.description` paragraph:

```tsx
                  {e.bullets?.length ? (
                    <ul className="type-ui mt-1 list-disc pl-5 text-muted-foreground">
                      {e.bullets.map((b, j) => <li key={j}>{b}</li>)}
                    </ul>
                  ) : e.description ? (
                    <p className="type-ui mt-1 text-muted-foreground">{e.description}</p>
                  ) : null}
```

Add a projects section directly after the experience section:

```tsx
        {(d.projects?.length ?? 0) > 0 && (
          <Section title={t('cv.projects')}>
            <ul className="flex flex-col gap-4">
              {d.projects!.map((p, i) => (
                <li key={i}>
                  <div className="flex flex-wrap items-baseline gap-x-2">
                    <span className="font-medium text-ink">{p.name}</span>
                    {p.kind && (
                      <span className="font-mono text-xs text-muted-foreground">{p.kind}</span>
                    )}
                  </div>
                  {p.technologies.length > 0 && (
                    <p className="type-ui mt-0.5 text-muted-foreground">
                      {p.technologies.join(' · ')}
                    </p>
                  )}
                  {p.bullets.length > 0 && (
                    <ul className="type-ui mt-1 list-disc pl-5 text-muted-foreground">
                      {p.bullets.map((b, j) => <li key={j}>{b}</li>)}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          </Section>
        )}
```

Replace the certifications section and add achievements after it:

```tsx
        {d.certifications.length > 0 && (
          <Section title={t('cv.certifications')}>
            <ul className="flex flex-col gap-1">
              {d.certifications.map((c, i) => <li key={i}>{certLabel(c)}</li>)}
            </ul>
          </Section>
        )}

        {(d.achievements?.length ?? 0) > 0 && (
          <Section title={t('cv.achievements')}>
            <ul className="list-disc pl-5">
              {d.achievements!.map((a, i) => <li key={i}>{a}</li>)}
            </ul>
          </Section>
        )}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\web && npm test -- cv/`
Expected: PASS.

- [ ] **Step 5: Run the whole web suite and the type check**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\web && npm test && npx tsc --noEmit`
Expected: PASS, no type errors.

- [ ] **Step 6: Commit**

```bash
git add web/src/app/\(app\)/cv web/src/messages/tr.json web/src/messages/en.json
git commit -m "feat(web): show projects, achievements and certificate issuers on the CV page"
```

---

### Task 11: End-to-end check against the real model

**Files:**
- Create: `api/tools/probe_ats.py`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing the code depends on — a manual verification script.

- [ ] **Step 1: Write the probe**

`api/tools/` already holds probe scripts; follow their shape. Create `api/tools/probe_ats.py`:

```python
"""Run one real ATS rewrite against Gemini and print what came back.

Not a test: it costs a request against DAILY_AI_LIMIT and needs a live key.
Run it once after the engine changes to see whether the model actually obeys
the rules — the unit tests only prove the plumbing.

    cd api && .venv\\Scripts\\python -m tools.probe_ats
"""
import json

from app.schemas import CVData
from app.services.ats import rewrite_ats
from app.services.llm import get_llm

SOURCE = CVData.model_validate({
    "full_name": "Ada Lovelace",
    "title": None,
    "email": "ada@example.com",
    "location": "London",
    "summary": "Hard-working and passionate developer seeking an opportunity.",
    "experiences": [{
        "title": "Intern", "company": "Analytical Engine Corp",
        "start_date": "2020", "end_date": "2021",
        "description": "Responsible for database operations and reporting.",
    }],
    "education": [{"degree": "BSc Mathematics", "school": "Cambridge", "year": "2019"}],
    "skills": ["Python", "SQL", "Docker", "teamwork"],
    "languages": ["English"],
    "certifications": ["AWS Solutions Architect"],
})

if __name__ == "__main__":
    out = rewrite_ats(SOURCE, "en", get_llm())
    print(json.dumps(out.model_dump(), indent=2, ensure_ascii=False))
```

- [ ] **Step 2: Run it and read the output**

Run: `cd C:\Users\ASUS\Desktop\cv-ai\api && .venv\Scripts\python -m tools.probe_ats`

Check by hand, and report each answer:
- Is the Intern role still an internship, not "Developer"?
- Did "Docker" land under a tools group rather than a programming-languages group, and did "teamwork" stay out of the technical groups?
- Did the summary lose "hard-working", "passionate" and "seeking an opportunity", and is it first person?
- Are the experience points in `bullets` with `description` empty?
- Did it invent any number, company or date absent from `SOURCE`?
- Is `verification_required` non-empty and actually about the source's gaps (the missing `title`, the certificate's missing issuer and date)?

- [ ] **Step 3: Commit**

```bash
git add api/tools/probe_ats.py
git commit -m "chore(api): probe the ATS rewrite against the real model"
```

- [ ] **Step 4: Report the probe output**

Paste the probe's JSON and the answers to the six questions above. If the model broke an accuracy rule, that is a prompt bug worth fixing before this branch merges — the rules are the whole point of the change.

---

## Verification

Before opening a PR:

```bash
cd C:\Users\ASUS\Desktop\cv-ai\api && .venv\Scripts\python -m pytest -q
cd C:\Users\ASUS\Desktop\cv-ai\web && npm test && npx tsc --noEmit && npm run lint
```

All four must pass, and the probe in Task 11 must have been run and its output read.
