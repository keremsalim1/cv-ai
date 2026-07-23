import base64
import logging
import tempfile
import time
from pathlib import Path

import trafilatura
from pydantic import BaseModel

from app.schemas import CVData, FieldAnswer, FormField, FormSchema
from app.services import ats
from app.services.browser import BrowserDriver
from app.services.llm import MODEL_SMART, LLMClient
from app.services.page_analysis import detect_captcha, detect_login, extract_form

logger = logging.getLogger(__name__)

LOGIN_WAIT_SECONDS = 180
LOGIN_POLL_SECONDS = 2

SYSTEM = (
    "You optimize a CV for one specific job application and answer its form. "
    "Input JSON: cv, job_text, form (fields with id/label/type/options). "
    "Respond ONLY with JSON: "
    '{{"cv": <optimized CV, same schema>, "changes": [str], '
    '"cover_letter": str, "answers": [{{"field_id": str, "value": str}}]}}. '
    "Rules: NEVER invent facts absent from the CV — only reorder, reword and "
    "emphasize. changes = short user-facing list of what you altered. "
    "cover_letter: always write one, first person, active voice, grounded in "
    "the CV and the posting. answers: one per form field except type=file; "
    "identity fields (name/email/phone/location) come from the CV; for "
    "select/radio pick EXACTLY one option verbatim from options; if the CV "
    "lacks the information, use value \"\" so the user fills it. "
    "Answer in language: {language}."
)


class PrepareOut(BaseModel):
    cv: CVData
    changes: list[str] = []
    cover_letter: str | None = None
    answers: list[FieldAnswer] = []


def _job_text(html: str) -> str:
    text = trafilatura.extract(html)
    if text:
        return text
    # trafilatura is picky on minimal pages; crude fallback keeps the flow alive
    from lxml import html as lxml_html
    return lxml_html.fromstring(html).text_content().strip()[:8000]


def _page_state(html: str) -> tuple[bool, FormSchema]:
    """(is_login_wall, form). A password field ALWAYS means login wall — a
    login form's surviving fields must never be mistaken for the application
    form (password inputs are filtered out of extract_form)."""
    return detect_login(html), extract_form(html)


def _wait_for_login(driver: BrowserDriver) -> tuple[str, FormSchema]:
    """Headed mode: user is logging in by hand; poll until the login wall is
    gone and an application form appears (or the wait times out)."""
    deadline = time.monotonic() + LOGIN_WAIT_SECONDS
    while True:
        html = driver.content()
        is_login, schema = _page_state(html)
        if (schema.fields and not is_login) or time.monotonic() > deadline:
            return html, schema
        time.sleep(LOGIN_POLL_SECONDS)


class PrepareIn(BaseModel):
    cv: CVData
    job_text: str
    form: list[FormField]


def prepare_application(cv: CVData, url: str, language: str, headed: bool,
                        llm: LLMClient, make_driver) -> dict:
    driver: BrowserDriver = make_driver(headed)
    try:
        driver.goto(url)
        html = driver.content()
        is_login, schema = _page_state(html)
        if headed and (is_login or not schema.fields):
            html, schema = _wait_for_login(driver)
            is_login = detect_login(html)
        if detect_captcha(html):
            return {"status": "captcha", "job_text": _job_text(html)}
        if is_login:
            return {"status": "login_required"}
        if not schema.fields:
            return {"status": "form_not_found", "job_text": _job_text(html)}

        job_text = _job_text(html)
        user_payload = PrepareIn(cv=cv, job_text=job_text,
                                 form=schema.fields).model_dump_json()
        out = llm.chat_json(MODEL_SMART, SYSTEM.format(language=language),
                            user_payload, PrepareOut)
        return {
            "status": "ready",
            "form": [f.model_dump() for f in schema.fields],
            "cv": out.cv.model_dump(),
            "changes": out.changes,
            "cover_letter": out.cover_letter,
            "answers": [a.model_dump() for a in out.answers],
            "job_text": job_text,
        }
    finally:
        driver.close()


def _fill_form(driver: BrowserDriver, schema: FormSchema,
               answers: list[FieldAnswer], pdf_path: str) -> None:
    values = {a.field_id: a.value for a in answers}
    for field in schema.fields:
        if field.type == "file":
            driver.set_files(field.selector, pdf_path)
            continue
        value = values.get(field.id, "")
        if not value:
            continue
        if field.type in ("text", "textarea"):
            driver.fill(field.selector, value)
        elif field.type == "select":
            driver.select_by_label(field.selector, value)
        elif field.type == "radio":
            if value in field.options:
                driver.click(field.option_selectors[field.options.index(value)])
        elif field.type == "checkbox":
            if value.lower() in ("yes", "true", "on", "evet", "1"):
                driver.click(field.selector)


def submit_application(cv: CVData, url: str, language: str,
                       answers: list[FieldAnswer], headed: bool,
                       make_driver) -> dict:
    pdf_bytes = ats.render_pdf(cv, language)
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(pdf_bytes)
    tmp.close()

    driver: BrowserDriver = make_driver(headed)
    try:
        driver.goto(url)
        html = driver.content()
        is_login, schema = _page_state(html)
        if headed and (is_login or not schema.fields):
            html, schema = _wait_for_login(driver)
            is_login = detect_login(html)
        if detect_captcha(html):
            return {"status": "captcha"}
        if is_login:
            return {"status": "login_required"}
        if not schema.fields:
            return {"status": "failed", "reason": "form_not_found"}

        _fill_form(driver, schema, answers, tmp.name)
        if schema.submit_selector:
            driver.click(schema.submit_selector)
        else:
            return {"status": "failed", "reason": "no_submit_button"}
        driver.wait(3_000)
        shot = base64.b64encode(driver.screenshot()).decode()
        return {"status": "submitted", "screenshot": shot}
    except Exception as exc:  # site quirks must not become a 500
        logger.warning("submit failed for %s: %s", url, exc)
        return {"status": "failed", "reason": str(exc)}
    finally:
        driver.close()
        Path(tmp.name).unlink(missing_ok=True)
