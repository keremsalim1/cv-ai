"""Turns raw observations into a FormSchema. Pure: no browser, no network, so
every rule here is testable against a captured inventory."""
import re

from app.schemas import FormField, FormSchema
from app.services.page_probe import RawControl

# Controls living in page chrome are never part of an application form.
CHROME_LANDMARKS = {"banner", "navigation", "search", "contentinfo"}
# Scopes in priority order: the modal the user is looking at beats the form,
# which beats the main region, which beats "everything we found".
SCOPES = ("dialog", "form", "main")

_TEXTUAL_ROLES = {"textbox", "searchbox", "spinbutton"}


def accessible_name(control: RawControl) -> str:
    for candidate in (control.labelledby_text, control.aria_label,
                      control.label_text, control.placeholder, control.name):
        if candidate and candidate.strip():
            return candidate.strip()
    return ""


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "field"


def _field_type(control: RawControl) -> str | None:
    role = control.role
    if role == "combobox":
        if control.tag == "select":
            return "select"
        return "typeahead" if control.autocomplete_hint in ("list", "both") else "combobox"
    if role == "listbox":
        return "listbox"
    if role in ("checkbox", "switch"):
        return "checkbox"
    if role == "radio":
        return "radio"
    if role == "file":
        return "file"
    if role in _TEXTUAL_ROLES:
        if control.tag == "textarea":
            return "textarea"
        return "date" if control.type == "date" else "text"
    # role=option is collected so fill strategies can find popup choices; a
    # choice is not a question, so it never becomes a field.
    return None


def _dropzone_refs(controls: list[RawControl]) -> set[str]:
    """Unlabelled file inputs that sit beside a labelled one. Portals like Ashby
    put an "autofill from your resume" dropzone above the real Resume field;
    uploading there makes them re-parse the CV and re-render the form, which
    empties the field the user actually applies with. A file input that is the
    only one we can see IS the resume field, label or not."""
    files = [c for c in controls if _field_type(c) == "file"]
    if not any(accessible_name(c) for c in files):
        return set()
    return {c.ref for c in files if not accessible_name(c)}


def _in_scope(controls: list[RawControl], platform=None) -> list[RawControl]:
    usable = [c for c in controls
              if c.visible and not c.disabled
              and c.role != "password"
              and c.landmark not in CHROME_LANDMARKS]
    scopes = (platform.scope_landmark,) if platform and platform.scope_landmark else SCOPES
    for scope in scopes:
        scoped = [c for c in usable if c.landmark == scope]
        if scoped:
            return scoped
    return usable


def build_form(controls: list[RawControl], platform=None) -> FormSchema:
    fields: list[FormField] = []
    used_ids: set[str] = set()
    radio_groups: dict[str, FormField] = {}

    def field_id(control: RawControl, label: str) -> str:
        base = control.name or _slug(label)
        candidate, n = base, 1
        while candidate in used_ids:
            n += 1
            candidate = f"{base}-{n}"
        used_ids.add(candidate)
        return candidate

    scoped = _in_scope(controls, platform)
    dropzones = _dropzone_refs(scoped)
    for control in scoped:
        ftype = _field_type(control)
        if ftype is None or control.ref in dropzones:
            continue
        label = accessible_name(control)
        selector = f'[data-cvai-ref="{control.ref}"]'

        if ftype == "radio":
            # One field per radio group; each member contributes an option.
            group = radio_groups.get(control.name)
            if group is None:
                group = FormField(id=field_id(control, label), selector=selector,
                                  frame=control.frame, label=label, type="radio",
                                  required=control.required)
                radio_groups[control.name] = group
                fields.append(group)
            group.options.append(label)
            group.option_selectors.append(selector)
            continue

        fields.append(FormField(
            id=field_id(control, label), selector=selector, frame=control.frame,
            label=label, type=ftype, options=list(control.options),
            required=control.required,
        ))

    # Assisted mode always hands the submit back to the user, so no schema we
    # build here may carry a submit target.
    return FormSchema(fields=fields, submit_selector=None)
