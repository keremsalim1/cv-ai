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
