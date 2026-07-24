"""Pure HTML analysis for application pages: no browser, no network."""
import re

from lxml import html as lxml_html

from app.schemas import FormField, FormSchema

_TEXT_INPUT_TYPES = {"text", "email", "tel", "url", "number", "date", None, ""}
_CAPTCHA_MARKERS = ("g-recaptcha", "h-captcha", "cf-turnstile", "recaptcha/api")


def detect_captcha(page_html: str) -> bool:
    return any(marker in page_html for marker in _CAPTCHA_MARKERS)


def detect_login(page_html: str) -> bool:
    doc = lxml_html.fromstring(page_html)
    return bool(doc.xpath("//input[@type='password']"))


def _label_text(el, doc) -> str:
    el_id = el.get("id")
    if el_id:
        labels = doc.xpath(f"//label[@for='{el_id}']")
        if labels:
            return labels[0].text_content().strip()
    parent = el.getparent()
    while parent is not None:
        if parent.tag == "label":
            return parent.text_content().strip()
        if parent.tag == "fieldset":
            legends = parent.xpath("./legend")
            if legends:
                return legends[0].text_content().strip()
        parent = parent.getparent()
    return (el.get("aria-label") or el.get("placeholder") or el.get("name") or "").strip()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "field"


def extract_form(page_html: str) -> FormSchema:
    doc = lxml_html.fromstring(page_html)
    tree = doc.getroottree()

    forms = doc.xpath("//form")
    best, best_count = None, 0
    for form in forms:
        # A form with a password field is a sign-in / create-account form, not
        # the job application form. Skipping it keeps a login widget (common in
        # page headers, even after login) from being mistaken for the form and
        # lets the real application form win.
        if form.xpath(".//input[@type='password']"):
            continue
        count = len(form.xpath(
            ".//input[not(@type='hidden')] | .//textarea | .//select"))
        if count > best_count:
            best, best_count = form, count
    # fewer than 2 visible controls: not an application form (search bars etc.)
    if best is None or best_count < 2:
        return FormSchema()

    fields: list[FormField] = []
    used_ids: set[str] = set()
    radios_done: set[str] = set()

    def field_id(el, label: str) -> str:
        base = el.get("name") or _slug(label)
        candidate, n = base, 1
        while candidate in used_ids:
            n += 1
            candidate = f"{base}-{n}"
        used_ids.add(candidate)
        return candidate

    for el in best.xpath(".//input | .//textarea | .//select"):
        tag = el.tag
        itype = (el.get("type") or "").lower()
        if tag == "input" and itype in ("hidden", "submit", "button", "password"):
            continue
        label = _label_text(el, doc)
        required = el.get("required") is not None or el.get("aria-required") == "true"
        selector = tree.getpath(el)

        if tag == "textarea":
            ftype, options, opt_sel = "textarea", [], []
        elif tag == "select":
            ftype = "select"
            options = [o.text_content().strip() for o in el.xpath("./option")
                       if o.text_content().strip()]
            opt_sel = []
        elif itype == "radio":
            name = el.get("name") or ""
            if name in radios_done:
                continue
            radios_done.add(name)
            group = best.xpath(f".//input[@type='radio'][@name='{name}']")
            ftype = "radio"
            options = [_label_text(r, doc) for r in group]
            opt_sel = [tree.getpath(r) for r in group]
            # group label: the fieldset legend, not the first choice's label
            legends = el.xpath("ancestor::fieldset/legend")
            if legends:
                label = legends[0].text_content().strip()
        elif itype == "checkbox":
            ftype, options, opt_sel = "checkbox", [], []
        elif itype == "file":
            ftype, options, opt_sel = "file", [], []
        elif itype in _TEXT_INPUT_TYPES:
            ftype, options, opt_sel = "text", [], []
        else:
            continue

        fields.append(FormField(
            id=field_id(el, label), selector=selector, label=label,
            type=ftype, options=options, option_selectors=opt_sel,
            required=required,
        ))

    submit = best.xpath(".//button[@type='submit'] | .//input[@type='submit'] | .//button[not(@type)]")
    submit_selector = tree.getpath(submit[0]) if submit else None
    return FormSchema(fields=fields, submit_selector=submit_selector)
