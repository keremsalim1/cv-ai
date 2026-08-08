import json
from pathlib import Path

import pytest

from app.services.inbox_classify import classify, classify_by_rules
from app.services.llm import LLMClient, LLMError
from app.services.mailbox import MailMessage
from tests.conftest import FakeOpenAI

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


# --- The LLM fallback -----------------------------------------------------

def llm_saying(payload: dict) -> LLMClient:
    return LLMClient(FakeOpenAI([json.dumps(payload)]))


def test_a_rule_hit_never_reaches_the_llm():
    fake = FakeOpenAI([])          # popping from an empty list would raise
    signal = classify(as_message(entries("rejected")[0]), LLMClient(fake))
    assert signal.stage == "rejected"
    assert fake.calls == []


def test_ambiguous_mail_is_resolved_by_the_llm():
    llm = llm_saying({"stage": "in_review", "company": "Acme", "title": "Backend Engineer",
                      "confidence": 0.8, "evidence": "süreçle ilgili güncelleme",
                      "job_related": True})
    signal = classify(as_message(entries("unsure")[0]), llm)
    assert signal.stage == "in_review"
    assert signal.company == "Acme"


def test_a_low_confidence_llm_answer_is_treated_as_unresolved():
    llm = llm_saying({"stage": "offer", "company": None, "title": None,
                      "confidence": 0.3, "evidence": "maybe", "job_related": True})
    assert classify(as_message(entries("unsure")[0]), llm).stage is None


def test_an_llm_answer_of_not_job_related_discards_the_mail():
    llm = llm_saying({"stage": None, "company": None, "title": None,
                      "confidence": 0.9, "evidence": "", "job_related": False})
    signal = classify(as_message(entries("unsure")[0]), llm)
    assert signal.job_related is False
    assert signal.stage is None


def test_an_llm_outage_leaves_the_stage_unresolved_instead_of_failing_the_sync():
    class Broken:
        def chat_json(self, *a, **k):
            raise LLMError("no quota")

    signal = classify(as_message(entries("unsure")[0]), Broken())
    assert signal.stage is None
    assert signal.job_related is True    # unknown, not disproven


def test_no_llm_available_still_returns_a_signal():
    assert classify(as_message(entries("unsure")[0]), None).stage is None


def test_the_llm_is_told_the_exact_stage_vocabulary():
    fake = FakeOpenAI([json.dumps({"stage": "received", "company": None, "title": None,
                                   "confidence": 0.9, "evidence": "x", "job_related": True})])
    classify(as_message(entries("unsure")[0]), LLMClient(fake))
    system = fake.calls[0]["messages"][0]["content"]
    for stage in ("received", "in_review", "interview", "offer", "rejected"):
        assert stage in system
