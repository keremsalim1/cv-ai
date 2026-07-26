import base64
import logging
import tempfile
import time
from pathlib import Path

import trafilatura
from pydantic import BaseModel

from app.config import get_settings
from app.schemas import CVData, FieldAnswer, FormField, FormSchema
from app.services import ats
from app.services.browser import BrowserDriver
from app.services.form_build import build_form
from app.services.llm import MODEL_SMART, LLMClient
from app.services.page_analysis import (detect_captcha, detect_login,
                                        extract_form)
from app.services.platforms import platform_for
from app.services.usage import enforce_limit, usage_store

logger = logging.getLogger(__name__)

LOGIN_WAIT_SECONDS = 180
LOGIN_POLL_SECONDS = 2
# Below this many characters of readable page text we treat the page as a bare
# login gate (nothing to optimize from); above it we optimize + deliver even if
# the page also offers a sign-in, so an optional login never blocks the user.
MIN_JOB_TEXT = 200

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
    "identity fields (name/email/phone/location, and the LinkedIn/GitHub/"
    "portfolio URLs from cv.linkedin/cv.github/cv.website) come from the CV; for "
    "select/radio pick EXACTLY one option verbatim from options; if the CV "
    "lacks the information, use value \"\" so the user fills it. "
    "Answer in language: {language}."
)


class PrepareOut(BaseModel):
    cv: CVData
    changes: list[str] = []
    cover_letter: str | None = None
    answers: list[FieldAnswer] = []


ASSIST_SYSTEM = (
    "You fill ONE page of a job application form from a CV. "
    "Input JSON: cv, job_text, form (fields with id/label/type/options). "
    'Respond ONLY with JSON: {{"answers": [{{"field_id": str, "value": str}}]}}. '
    "One answer per field except type=file. Identity fields "
    "(name/email/phone/location) come from the CV. A field asking for a "
    "LinkedIn, GitHub or portfolio/website URL is answered from cv.linkedin, "
    "cv.github and cv.website respectively. For select/radio pick EXACTLY "
    "one option verbatim from options. If the CV lacks the info, use value \"\" so "
    "the user fills it. NEVER invent facts. Answer in language: {language}."
)


class AssistIn(BaseModel):
    cv: CVData
    job_text: str
    form: list[FormField]


class AnswersOut(BaseModel):
    answers: list[FieldAnswer] = []


def _job_text(html: str) -> str:
    text = trafilatura.extract(html)
    if text:
        return text
    # trafilatura is picky on minimal pages; crude fallback keeps the flow alive
    from lxml import html as lxml_html
    return lxml_html.fromstring(html).text_content().strip()[:8000]


def _page_state(html: str) -> tuple[bool, FormSchema]:
    """(is_login_wall, form). A login wall blocks us ONLY when there is no
    application form to fill: a password field alongside a real form (or a
    header sign-in widget) is an *optional* login, not a wall."""
    schema = extract_form(html)
    return (detect_login(html) and not schema.fields), schema


def _wait_for_login(driver: BrowserDriver) -> tuple[str, FormSchema]:
    """Headed mode: the user is signing in by hand. Poll until an application
    form appears OR the login wall clears (or the wait times out), so we never
    hang once the user is through."""
    start = time.monotonic()
    deadline = start + LOGIN_WAIT_SECONDS
    logger.warning("[apply] wait_for_login: polling up to %ss", LOGIN_WAIT_SECONDS)
    while True:
        html = driver.content()
        schema = extract_form(html)
        raw_login = detect_login(html)
        elapsed = time.monotonic() - start
        if schema.fields or not raw_login:
            logger.warning("[apply] wait_for_login: proceeding after %.0fs "
                           "(login=%s, fields=%d)", elapsed, raw_login,
                           len(schema.fields))
            return html, schema
        if time.monotonic() > deadline:
            logger.warning("[apply] wait_for_login: TIMED OUT after %.0fs "
                           "(login=%s, fields=%d)", elapsed, raw_login,
                           len(schema.fields))
            return html, schema
        time.sleep(LOGIN_POLL_SECONDS)


class PrepareIn(BaseModel):
    cv: CVData
    job_text: str
    form: list[FormField]


def prepare_application(cv: CVData, url: str, language: str, headed: bool,
                        llm: LLMClient, make_driver, user_id: str) -> dict:
    driver: BrowserDriver = make_driver(headed)
    try:
        driver.goto(url)
        html = driver.content()
        is_login, schema = _page_state(html)
        logger.warning("[apply] prepare url=%s headed=%s initial is_login=%s "
                       "fields=%d captcha=%s", url, headed, is_login,
                       len(schema.fields), detect_captcha(html))
        if headed and (is_login or not schema.fields):
            html, schema = _wait_for_login(driver)
            is_login, schema = _page_state(html)

        # Only a BARE login wall — a sign-in page with no form and no readable
        # posting — forces the user to log in. If we can read the job (even when
        # the page also shows an optional sign-in, like Siemens/Avature portals),
        # we optimize and deliver instead of looping on login.
        job_text = _job_text(html)
        if is_login and len(job_text) < MIN_JOB_TEXT:
            logger.warning("[apply] prepare url=%s -> login_required "
                           "(bare login wall, job_text=%d)", url, len(job_text))
            return {"status": "login_required"}

        # The page IS usable. Optimize + answer in one LLM call regardless of
        # captcha/form presence; `status` only signals whether auto-submit works.
        if detect_captcha(html):
            status = "captcha"
        elif not schema.fields:
            status = "form_not_found"
        else:
            status = "ready"

        # Charge one AI credit now that we're actually calling the LLM.
        enforce_limit(usage_store, user_id, get_settings().daily_ai_limit)
        user_payload = PrepareIn(cv=cv, job_text=job_text,
                                 form=schema.fields).model_dump_json()
        out = llm.chat_json(MODEL_SMART, SYSTEM.format(language=language),
                            user_payload, PrepareOut)
        return {
            "status": status,
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
        # One unfillable field (stale selector, option not on the live page)
        # must not abort the whole submission — log it and keep going.
        try:
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
                # set_checked is idempotent, so a box pre-checked by the site
                # ends up matching the user's answer either way.
                driver.set_checked(field.selector,
                                   value.lower() in ("yes", "true", "on", "evet", "1"))
        except Exception as exc:
            logger.warning("could not fill field %s (%s): %s",
                           field.id, field.type, exc)


def submit_application(cv: CVData, url: str, language: str,
                       answers: list[FieldAnswer], headed: bool,
                       make_driver) -> dict:
    pdf_bytes = ats.render_pdf(cv, language)
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(pdf_bytes)
    tmp.close()

    # make_driver is inside the try so a browser-launch failure returns a clean
    # "failed" status AND still runs the finally that unlinks the temp PDF.
    driver: BrowserDriver | None = None
    try:
        driver = make_driver(headed)
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
        if driver is not None:
            driver.close()
        Path(tmp.name).unlink(missing_ok=True)


def _no_form_reason(html: str, controls: list) -> str:
    if detect_captcha(html):
        return "captcha"
    if detect_login(html):
        return "login_wall"
    return "no_controls" if not controls else "unsupported"


def assist_fill(session, cv: CVData, language: str,
                llm: LLMClient, user_id: str) -> dict:
    """Fill the CURRENT live page of an assisted session. Reads whatever the
    user navigated to by role, so shadow DOM and custom widgets are visible
    where parsing the HTML string saw nothing."""
    controls = session.probe()
    schema = build_form(controls, platform_for(session.url()))
    if not schema.fields:
        html = session.snapshot()
        reason = _no_form_reason(html, controls)
        logger.warning("[assist] no_form reason=%s controls=%d",
                       reason, len(controls))
        return {"status": "no_form", "reason": reason}
    # Real form present: charge one credit, then answer + fill.
    enforce_limit(usage_store, user_id, get_settings().daily_ai_limit)
    job_text = _job_text(session.snapshot())
    user_payload = AssistIn(cv=cv, job_text=job_text,
                            form=schema.fields).model_dump_json()
    out = llm.chat_json(MODEL_SMART, ASSIST_SYSTEM.format(language=language),
                        user_payload, AnswersOut)
    pdf_bytes = ats.render_pdf(cv, language)
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(pdf_bytes)
    tmp.close()
    try:
        outcomes = session.fill_verified(schema, out.answers, tmp.name)
        shot = base64.b64encode(session.screenshot()).decode()
    finally:
        # Unlike submit_application, the assisted browser stays open, so it still
        # holds the uploaded PDF (Windows locks it). A successful fill must not
        # be reported as a failure over a leftover temp file.
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("temp PDF still held by the browser, leaving it "
                           "to the OS temp dir: %s (%s)", tmp.name, exc)
    filled = [{"label": o.label, "value": o.value}
              for o in outcomes if o.status == "filled"]
    unfilled = [{"label": o.label, "reason": o.reason}
                for o in outcomes if o.status == "failed"]
    return {"status": "filled", "filled": filled, "unfilled": unfilled,
            "field_count": len(schema.fields), "screenshot": shot}
