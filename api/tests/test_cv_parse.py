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


def test_parse_cv_null_degree(client, auth_headers, sample_pdf_bytes):
    # Regression: LLM returning null for an education degree used to 502.
    import json
    cv = json.loads(SAMPLE_CV_JSON)
    cv["education"].append({"degree": None, "school": "Anadolu Lisesi", "year": None})
    override_llm([json.dumps(cv)])
    r = client.post("/cv/parse", headers=auth_headers,
                    files={"file": ("cv.pdf", sample_pdf_bytes, "application/pdf")})
    assert r.status_code == 200
    assert r.json()["cv"]["education"][-1]["degree"] is None


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
