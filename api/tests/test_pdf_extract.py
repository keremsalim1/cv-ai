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
