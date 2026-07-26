import json

from app.schemas import CVData, SkillGroup
from app.services.ats import render_pdf
from tests.conftest import SAMPLE_CV_JSON, override_llm


def _cv() -> CVData:
    return CVData.model_validate_json(SAMPLE_CV_JSON)


def test_render_pdf_produces_pdf():
    pdf = render_pdf(_cv(), "en")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


def test_render_pdf_title_and_header_text():
    import pymupdf

    cv = _cv()
    cv.title = "Software Engineer"
    pdf = render_pdf(cv, "en")
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    text = doc[0].get_text()
    assert "Ada Lovelace" in text
    assert "Software Engineer" in text
    assert "London" in text and "ada@example.com" in text


def test_render_pdf_includes_profile_links():
    import pymupdf

    cv = _cv()
    cv.linkedin = "linkedin.com/in/ada"
    cv.github = "github.com/ada"
    pdf = render_pdf(cv, "en")
    text = pymupdf.open(stream=pdf, filetype="pdf")[0].get_text()
    assert "linkedin.com/in/ada" in text
    assert "github.com/ada" in text


def test_render_pdf_education_without_degree():
    import pymupdf

    cv = _cv()
    cv.education[0].degree = None
    pdf = render_pdf(cv, "en")
    text = pymupdf.open(stream=pdf, filetype="pdf")[0].get_text()
    assert "None" not in text
    assert cv.education[0].school in text


def test_render_pdf_turkish_chars():
    cv = _cv()
    cv.full_name = "Şükrü Çağrı Öğüt"
    cv.summary = "Gömülü yazılım geliştirici; İstanbul'da 5 yıl deneyim."
    pdf = render_pdf(cv, "tr")
    assert pdf.startswith(b"%PDF")


def test_render_pdf_grouped_skills():
    import pymupdf

    cv = _cv()
    cv.skill_groups = [
        SkillGroup(name="Programming Languages", skills=["Python", "C"]),
        SkillGroup(name="Soft Skills", skills=["Leadership"]),
        SkillGroup(name="Empty Group", skills=[]),
    ]
    pdf = render_pdf(cv, "en")
    text = pymupdf.open(stream=pdf, filetype="pdf")[0].get_text()
    assert "Programming Languages" in text
    assert "Python, C" in text
    assert "Leadership" in text
    assert "Empty Group" not in text


def test_rewrite_endpoint_accepts_category_alias(client, auth_headers):
    # Gemini labels groups "category" despite the prompt; must not 502
    rewritten = json.loads(SAMPLE_CV_JSON)
    rewritten["skill_groups"] = [
        {"category": "Programlama Dilleri", "skills": ["Python", "C"]},
    ]
    override_llm([json.dumps(rewritten)])
    r = client.post("/ats/rewrite", headers=auth_headers,
                    json={"cv": json.loads(SAMPLE_CV_JSON), "language": "tr"})
    assert r.status_code == 200
    assert r.json()["cv"]["skill_groups"][0]["name"] == "Programlama Dilleri"


def test_rewrite_endpoint_returns_skill_groups(client, auth_headers):
    rewritten = json.loads(SAMPLE_CV_JSON)
    rewritten["skill_groups"] = [
        {"name": "Programming Languages", "skills": ["Python"]},
    ]
    override_llm([json.dumps(rewritten)])
    r = client.post("/ats/rewrite", headers=auth_headers,
                    json={"cv": json.loads(SAMPLE_CV_JSON), "language": "en"})
    assert r.status_code == 200
    assert r.json()["cv"]["skill_groups"][0]["name"] == "Programming Languages"


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
