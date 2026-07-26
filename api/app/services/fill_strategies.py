"""How to put a value into one control. Custom widgets are not <select>s: they
open a popup rendered somewhere else in the document, so picking an option means
clicking twice with a re-read in between."""
import logging

from app.schemas import FieldOutcome, FormField
from app.services.page_probe import PROBE_JS, RawControl

logger = logging.getLogger(__name__)

TRUTHY = ("yes", "true", "on", "evet", "1")


def _visible_options(driver, frame: int) -> list[RawControl]:
    """Re-read the page for popup options. They are usually rendered at the
    document root rather than inside the combobox, so scoping to the control
    would miss them."""
    raw = driver.evaluate(f"({PROBE_JS})({frame})", frame=frame) or []
    controls = [RawControl(**c) for c in raw]
    return [c for c in controls if c.role == "option"]


def _option_label(control: RawControl) -> str:
    return (control.label_text or control.aria_label
            or control.labelledby_text or "").strip()


def _pick_option(driver, field: FormField, value: str) -> None:
    for option in _visible_options(driver, field.frame):
        if _option_label(option).casefold() == value.casefold():
            driver.click(f'[data-cvai-ref="{option.ref}"]', frame=option.frame)
            return
    raise LookupError(f"no visible option matched {value!r}")


def fill_field(driver, field: FormField, value: str, pdf_path: str) -> FieldOutcome:
    def outcome(status: str, reason: str = "") -> FieldOutcome:
        return FieldOutcome(field_id=field.id, label=field.label, value=value,
                            status=status, reason=reason)

    if field.type == "file":
        try:
            driver.set_files(field.selector, pdf_path, frame=field.frame)
            return outcome("filled")
        except Exception as exc:
            return outcome("failed", str(exc))

    if not value:
        # The LLM answers "" when the CV does not carry the information; the
        # user fills those in themselves, so this is not a failure.
        return outcome("skipped", "no answer")

    try:
        if field.type in ("text", "textarea", "date"):
            driver.fill(field.selector, value, frame=field.frame)
        elif field.type == "select":
            driver.select_by_label(field.selector, value, frame=field.frame)
        elif field.type == "checkbox":
            driver.set_checked(field.selector, value.casefold() in TRUTHY,
                               frame=field.frame)
        elif field.type == "radio":
            if value not in field.options:
                return outcome("failed", f"{value!r} is not one of the choices")
            driver.click(field.option_selectors[field.options.index(value)],
                         frame=field.frame)
        elif field.type == "typeahead":
            driver.fill(field.selector, value, frame=field.frame)
            _pick_option(driver, field, value)
        elif field.type in ("combobox", "listbox"):
            driver.click(field.selector, frame=field.frame)
            _pick_option(driver, field, value)
        else:
            return outcome("failed", f"no strategy for type {field.type!r}")
    except Exception as exc:
        logger.warning("[fill] %s (%s): %s", field.id, field.type, exc)
        return outcome("failed", str(exc))
    return outcome("filled")
