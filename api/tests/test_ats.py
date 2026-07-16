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
