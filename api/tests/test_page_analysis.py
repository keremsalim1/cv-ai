from pathlib import Path

from app.services.page_analysis import detect_captcha, detect_login, extract_form

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_extract_form_fields_and_types():
    schema = extract_form(_read("greenhouse_like.html"))
    by_id = {f.id: f for f in schema.fields}
    assert by_id["full_name"].type == "text"
    assert by_id["full_name"].required is True
    assert by_id["full_name"].label == "Full name"
    assert by_id["email"].type == "text"
    assert by_id["resume"].type == "file"
    assert by_id["motivation"].type == "textarea"
    assert by_id["experience"].type == "select"
    assert by_id["experience"].options == ["0-1", "1-3", "3-5", "5+"]
    assert by_id["permit"].type == "radio"
    assert by_id["permit"].options == ["Yes", "No"]
    assert len(by_id["permit"].option_selectors) == 2
    assert by_id["kvkk"].type == "checkbox"
    # hidden inputs and the tiny search form are ignored
    assert "token" not in by_id
    assert "q" not in by_id


def test_extract_form_picks_biggest_form_and_submit():
    schema = extract_form(_read("greenhouse_like.html"))
    assert schema.submit_selector is not None
    assert "button" in schema.submit_selector


def test_extract_form_selectors_are_xpaths():
    schema = extract_form(_read("greenhouse_like.html"))
    assert all(f.selector.startswith("/") for f in schema.fields)


def test_no_form_returns_empty():
    assert extract_form("<html><body><p>hi</p></body></html>").fields == []


def test_detect_login():
    assert detect_login(_read("login_wall.html")) is True
    assert detect_login(_read("greenhouse_like.html")) is False


def test_detect_captcha():
    assert detect_captcha(_read("captcha_page.html")) is True
    assert detect_captcha(_read("greenhouse_like.html")) is False
