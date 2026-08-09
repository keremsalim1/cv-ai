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
    override_llm([json.dumps({"cv": rewritten})])
    r = client.post("/ats/rewrite", headers=auth_headers,
                    json={"cv": json.loads(SAMPLE_CV_JSON), "language": "tr"})
    assert r.status_code == 200
    assert r.json()["cv"]["skill_groups"][0]["name"] == "Programlama Dilleri"


def test_rewrite_endpoint_returns_skill_groups(client, auth_headers):
    rewritten = json.loads(SAMPLE_CV_JSON)
    rewritten["skill_groups"] = [
        {"name": "Programming Languages", "skills": ["Python"]},
    ]
    override_llm([json.dumps({"cv": rewritten})])
    r = client.post("/ats/rewrite", headers=auth_headers,
                    json={"cv": json.loads(SAMPLE_CV_JSON), "language": "en"})
    assert r.status_code == 200
    assert r.json()["cv"]["skill_groups"][0]["name"] == "Programming Languages"


def test_rewrite_endpoint(client, auth_headers):
    override_llm([json.dumps({"cv": json.loads(SAMPLE_CV_JSON)})])
    r = client.post("/ats/rewrite", headers=auth_headers,
                    json={"cv": json.loads(SAMPLE_CV_JSON), "language": "en"})
    assert r.status_code == 200
    assert r.json()["cv"]["full_name"] == "Ada Lovelace"


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


def test_pdf_endpoint(client, auth_headers):
    r = client.post("/ats/pdf", headers=auth_headers,
                    json={"cv": json.loads(SAMPLE_CV_JSON), "language": "tr"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")


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
