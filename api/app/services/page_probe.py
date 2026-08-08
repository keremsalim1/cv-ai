"""Runs the collector in every frame and returns raw observations.

The collector decides nothing: it reports what it saw and stamps each control
with an addressable ref. All naming, typing and scoping policy lives in
form_build, where it can be tested without a browser."""
import logging
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

PROBE_JS = (Path(__file__).parent / "probe.js").read_text(encoding="utf-8")


class RawControl(BaseModel):
    ref: str
    frame: int = 0
    tag: str = ""
    type: str = ""
    role: str = ""
    aria_label: str = ""
    labelledby_text: str = ""
    label_text: str = ""
    placeholder: str = ""
    name: str = ""
    value: str = ""
    required: bool = False
    disabled: bool = False
    visible: bool = True
    options: list[str] = []
    landmark: str = ""
    autocomplete_hint: str = ""


def probe_controls(driver) -> list[RawControl]:
    controls: list[RawControl] = []
    for frame in range(driver.frame_count()):
        try:
            raw = driver.evaluate(f"({PROBE_JS})({frame})", frame=frame)
        except Exception as exc:
            # A frame we cannot reach must not blank the whole page; the fields
            # we did find are still worth filling.
            logger.warning("[probe] frame %d unreadable: %s", frame, exc)
            continue
        controls.extend(RawControl(**c) for c in raw or [])
    return controls
