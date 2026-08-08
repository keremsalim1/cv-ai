from pathlib import Path

from app.services.page_analysis import (detect_blocked, detect_captcha,
                                        detect_login, extract_form)

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


def test_selector_prefers_a_unique_id_over_a_positional_path():
    # React portals re-render between snapshot and fill; a positional path goes
    # stale, an id survives. (LinkedIn's controls carry useId values like ":ra:".)
    schema = extract_form(_read("dialog_no_form.html"))
    by_id = {f.id: f for f in schema.fields}
    assert by_id["mobile-phone-number"].selector == '//*[@id="d-phone"]'
    assert by_id["email-address"].selector == '//*[@id="d-email"]'


def test_selector_falls_back_to_a_path_without_a_usable_id():
    page = ("<html><body><form>"
            "<label>A<input name='a'></label>"
            "<label>B<input name='b' id='dup'></label>"
            "<label>C<input name='c' id='dup'></label>"
            "</form></body></html>")
    by_id = {f.id: f for f in extract_form(page).fields}
    assert by_id["a"].selector.startswith("/html")      # no id at all
    assert by_id["b"].selector.startswith("/html")      # id is not unique


def test_no_form_returns_empty():
    assert extract_form("<html><body><p>hi</p></body></html>").fields == []


def test_extract_form_falls_back_to_dialog_when_page_has_no_form():
    # LinkedIn Easy Apply: no <form> anywhere, application inside a <dialog>.
    schema = extract_form(_read("dialog_no_form.html"))
    by_id = {f.id: f for f in schema.fields}
    assert len(schema.fields) == 4
    assert by_id["email-address"].type == "select"
    assert by_id["email-address"].options == ["ada@example.com", "ada.lovelace@work.com"]
    assert by_id["mobile-phone-number"].type == "text"
    assert by_id["how-many-years-of-work-experience-do-you-have-with-react"].type == "text"
    # page chrome outside the dialog must stay out
    assert "global-search" not in by_id
    assert not any("Arama yap" in f.label for f in schema.fields)
    assert not any(f.id == "lang-picker" for f in schema.fields)


def test_dialog_fallback_never_offers_a_submit_button():
    # "İleri" advances a step; auto-clicking it would skip the user's review.
    assert extract_form(_read("dialog_no_form.html")).submit_selector is None


def test_real_form_wins_over_a_dialog_on_the_same_page():
    page = _read("greenhouse_like.html").replace(
        "</body>", "<dialog open><label for='x'>Cookie choice</label>"
                   "<input id='x'><input id='y'></dialog></body>")
    schema = extract_form(page)
    by_id = {f.id: f for f in schema.fields}
    assert "full_name" in by_id
    assert schema.submit_selector is not None


def test_detect_login():
    assert detect_login(_read("login_wall.html")) is True
    assert detect_login(_read("greenhouse_like.html")) is False


def test_detect_captcha():
    assert detect_captcha(_read("captcha_page.html")) is True
    assert detect_captcha(_read("greenhouse_like.html")) is False


def test_a_hard_block_is_not_a_page_the_user_can_navigate_out_of():
    # Reported as "no fields found" it reads as "go to the form and retry",
    # advice that cannot work: the request was refused, there is no form.
    assert detect_blocked(_read("blocked_page.html")) is True


def test_a_block_is_not_offered_to_the_user_as_a_captcha():
    # nothing on that page is solvable, so telling them to solve it is a lie
    assert detect_captcha(_read("blocked_page.html")) is False


def test_a_challenge_carrying_a_widget_stays_a_captcha():
    # both pages ship the same cdn-cgi scripts; the widget is what separates
    # "you can clear this yourself" from "you were refused"
    html = _read("cloudflare_challenge_page.html")
    assert detect_captcha(html) is True
    assert detect_blocked(html) is False


def test_an_ordinary_application_page_is_neither():
    assert detect_blocked(_read("greenhouse_like.html")) is False
