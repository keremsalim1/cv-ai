"""Stages move forward only, and rejection ends the story.

Mail arrival order is not event order: ATS acknowledgements are routinely
delivered late, and letting one rewind an interview badge would make the whole
feature look broken.
"""

STAGE_ORDER: dict[str, int] = {
    "received": 1, "in_review": 2, "interview": 3, "offer": 4,
}
TERMINAL = "rejected"


def next_stage(current: str | None, detected: str | None) -> str | None:
    """The stage to store, or None when the application should not change."""
    if detected is None:
        return None
    if detected != TERMINAL and detected not in STAGE_ORDER:
        return None          # not a stage we recognise; refuse to store it
    if current == TERMINAL:
        return None
    if detected == TERMINAL:
        return TERMINAL
    if current is None:
        return detected
    if current not in STAGE_ORDER:
        return None          # same refusal, from the other side
    return detected if STAGE_ORDER[detected] > STAGE_ORDER[current] else None
