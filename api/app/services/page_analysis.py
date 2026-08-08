"""Pure HTML analysis for application pages: no browser, no network."""
import re

from lxml import html as lxml_html

from app.schemas import FormField, FormSchema

_TEXT_INPUT_TYPES = {"text", "email", "tel", "url", "number", "date", None, ""}
_CAPTCHA_MARKERS = ("g-recaptcha", "h-captcha", "cf-turnstile", "recaptcha/api")
# A refusal ships the same challenge scripts as a solvable check but no widget.
_BLOCK_MARKERS = ("/cdn-cgi/challenge-platform", "Ray ID")


def detect_captcha(page_html: str) -> bool:
    return any(marker in page_html for marker in _CAPTCHA_MARKERS)


def detect_blocked(page_html: str) -> bool:
    """The edge refused the request outright. Distinct from a captcha, and the
    distinction is the whole point: a captcha is something the user can clear,
    a block is not, so telling them to solve it or to navigate onward is advice
    that cannot work."""
    if detect_captcha(page_html):
        return False
    return any(marker in page_html for marker in _BLOCK_MARKERS)


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


def form_debug(page_html: str) -> str:
    """Why did extract_form find nothing? Summarize the page's real controls."""
    doc = lxml_html.fromstring(page_html)
    forms = doc.xpath("//form")
    parts = [f"forms={len(forms)}"]
    for i, form in enumerate(forms):
        controls = form.xpath(".//input[not(@type='hidden')] | .//textarea | .//select")
        has_pw = bool(form.xpath(".//input[@type='password']"))
        types = [c.tag if c.tag != "input" else (c.get("type") or "text")
                 for c in controls][:8]
        parts.append(f"form[{i}]: controls={len(controls)} pw={has_pw} types={types}")
    all_controls = doc.xpath("//input[not(@type='hidden')] | //textarea | //select")
    orphans = [c for c in all_controls if not c.xpath("ancestor::form")]
    parts.append(f"controls_total={len(all_controls)} outside_any_form={len(orphans)}")
    parts.append("orphan_labels=" + str(
        [(c.tag, (c.get("type") or ""), (c.get("aria-label") or c.get("name")
          or c.get("placeholder") or "")[:40]) for c in orphans][:10]))
    return " | ".join(parts)


def _selector(el, tree, doc) -> str:
    """Prefer a unique id over a positional path. Single-page portals re-render
    between the snapshot we analyse and the moment we fill, which silently
    invalidates /html/body/div[3]/... — an id survives the re-render."""
    el_id = el.get("id")
    if el_id and '"' not in el_id and len(doc.xpath(f'//*[@id="{el_id}"]')) == 1:
        return f'//*[@id="{el_id}"]'
    return tree.getpath(el)


def _controls(el):
    return el.xpath(".//input[not(@type='hidden')] | .//textarea | .//select")


def _best_dialog(doc):
    """The open modal with the most controls. Portals like LinkedIn Easy Apply
    render their application inside a <dialog> with no <form> element at all;
    scoping to the dialog keeps page chrome (search box, language picker) out."""
    best, best_count = None, 0
    for dialog in doc.xpath("//dialog[@open] | //*[@role='dialog'] "
                            "| //*[@aria-modal='true']"):
        if dialog.xpath(".//input[@type='password']"):
            continue
        count = len(_controls(dialog))
        if count > best_count:
            best, best_count = dialog, count
    return best, best_count


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
        count = len(_controls(form))
        if count > best_count:
            best, best_count = form, count
    # fewer than 2 visible controls: not an application form (search bars etc.)
    real_form = best is not None and best_count >= 2
    if not real_form:
        # No usable <form>. Fall back to the open dialog the user is looking at;
        # one control is enough there, since a modal step may ask a single
        # question ("years of experience with React?").
        best, best_count = _best_dialog(doc)
        if best is None or best_count < 1:
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
        selector = _selector(el, tree, doc)

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
            opt_sel = [_selector(r, tree, doc) for r in group]
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

    # Only a real <form> may be auto-submitted. A dialog's primary button is
    # usually "Next" in a multi-step flow — clicking it would skip the user's
    # review, so assisted mode always hands the submit back to the user.
    submit_selector = None
    if real_form:
        submit = best.xpath(".//button[@type='submit'] | .//input[@type='submit'] "
                            "| .//button[not(@type)]")
        submit_selector = tree.getpath(submit[0]) if submit else None
    return FormSchema(fields=fields, submit_selector=submit_selector)
