import json
from pathlib import Path

import pytest

from app.services.inbox_classify import classify_by_rules
from app.services.mailbox import MailMessage

CORPUS = json.loads(
    (Path(__file__).parent / "fixtures" / "mail" / "corpus.json").read_text(encoding="utf-8")
)


def as_message(entry: dict) -> MailMessage:
    return MailMessage(
        message_id=entry["id"], thread_id="t-" + entry["id"],
        from_address=entry["from"], subject=entry["subject"],
        received_at="2026-07-27T10:00:00+00:00", body=entry["body"],
        has_calendar_invite=entry["calendar"],
    )


def entries(expect: str) -> list[dict]:
    return [e for e in CORPUS if e["expect"] == expect]


@pytest.mark.parametrize("entry", [e for e in CORPUS if e["expect"] not in ("unsure", "ignore")],
                         ids=lambda e: e["id"])
def test_rules_read_the_stage_from_real_ats_wording(entry):
    signal = classify_by_rules(as_message(entry))
    assert signal is not None, f"{entry['id']} produced no rule hit"
    assert signal.stage == entry["expect"]
    assert signal.evidence, "a stage without evidence cannot be justified to the user"


@pytest.mark.parametrize("entry", entries("ignore"), ids=lambda e: e["id"])
def test_non_application_mail_is_marked_not_job_related_or_left_unsure(entry):
    signal = classify_by_rules(as_message(entry))
    assert signal is None or signal.job_related is False


@pytest.mark.parametrize("entry", entries("unsure"), ids=lambda e: e["id"])
def test_vague_mail_abstains_rather_than_guessing(entry):
    assert classify_by_rules(as_message(entry)) is None


def test_rejection_wins_over_an_acknowledgement_in_the_same_mail():
    # ATS rejections routinely restate "we received your application" first.
    msg = as_message({
        "id": "mixed", "from": "no-reply@greenhouse.io", "subject": "Update",
        "body": ("We have received your application for Backend Engineer. "
                 "After review we have decided to move forward with other candidates."),
        "calendar": False,
    })
    assert classify_by_rules(msg).stage == "rejected"


def test_a_calendar_invite_alone_is_not_enough_to_call_it_an_interview():
    # Automated "add this to your calendar" footers exist; require wording too.
    msg = as_message({
        "id": "cal-only", "from": "ik@initech.com.tr", "subject": "Bilgilendirme",
        "body": "Merhaba, sürece dair genel bir bilgilendirme.", "calendar": True,
    })
    assert classify_by_rules(msg) is None


def test_the_evidence_is_the_sentence_that_decided_it():
    signal = classify_by_rules(as_message(entries("rejected")[0]))
    assert "move forward with other candidates" in signal.evidence.lower()
