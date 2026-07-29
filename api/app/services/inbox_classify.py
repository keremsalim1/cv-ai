"""Turning a mail into a stage.

Rules first: ATS templates are near-identical across employers, so most mail is
classifiable for free. The LLM (added in the next task) only sees what the rules
cannot settle. Silence is a valid answer — a wrong badge costs the user more
than a missing one.
"""
import logging
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from app.services.llm import MODEL_FAST, LLMClient, LLMError
from app.services.mailbox import ATS_DOMAINS, MailMessage

logger = logging.getLogger(__name__)

Stage = Literal["received", "in_review", "interview", "offer", "rejected"]

# Ordered most-decisive first: the first stage with a hit wins, which is why
# rejection outranks the acknowledgement wording ATS mails repeat above it.
STAGE_PATTERNS: tuple[tuple[Stage, tuple[str, ...]], ...] = (
    ("rejected", (
        r"move forward with other candidate",
        r"decided not to (proceed|move forward)",
        r"unfortunately.{0,40}(not|unable to) (be )?(proceed|continu|select)",
        r"will not be moving forward",
        r"olumsuz sonu[çc]lan",
        r"ba[şs]ka adaylarla (devam|ilerle)",
        r"de[ğg]erlendirmeye alamad",
        r"uygun bulunma",
    )),
    ("offer", (
        r"pleased to offer",
        r"we are happy to offer",
        r"offer letter",
        r"i[şs] teklif",
        r"teklifimizi sunmak",
    )),
    ("interview", (
        r"interview invitation",
        r"invite you to (an? )?(interview|conversation)",
        r"schedule a call",
        r"book a time",
        r"m[üu]lakat(a)? davet",
        r"g[öo]r[üu][şs]meye davet",
        r"teknik m[üu]lakat",
    )),
    ("in_review", (
        r"shortlisted",
        r"next stage",
        r"moving you (on )?to the next",
        r"under review by",
        r"de[ğg]erlendirmeye al[ıi]nd",
        r"bir sonraki a[şs]ama",
        r"s[üu]reciniz devam ediyor",
    )),
    ("received", (
        r"we have received your application",
        r"thanks? for applying",
        r"thank you for applying",
        r"application (has been )?received",
        r"ba[şs]vurunuz al[ıi]n",
        r"ba[şs]vurunuz i[çc]in te[şs]ekk[üu]r",
    )),
)

# Mail that mentions jobs but is not a response to one of ours.
NOT_A_RESPONSE: tuple[str, ...] = (
    r"new jobs? (for|matching)",
    r"recommended (jobs?|positions?)",
    r"jobs? (alert|digest)",
    r"came across your profile",
    r"would you be open to",
    r"yeni i[şs] ilanlar",
)

_COMPANY_FROM_SUBJECT = re.compile(
    r"(?:application to|apply to|position at|offer[^-]*at)\s+([A-Z][\w&.\- ]{1,40})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Signal:
    stage: Stage | None
    company: str | None
    title: str | None
    confidence: float
    evidence: str
    job_related: bool


def _haystack(msg: MailMessage) -> str:
    return f"{msg.subject}\n{msg.body[:2000]}"


def _sentence_containing(text: str, match: re.Match) -> str:
    start = text.rfind(".", 0, match.start()) + 1
    end = text.find(".", match.end())
    end = len(text) if end == -1 else end + 1
    return text[start:end].strip()


def _from_ats(msg: MailMessage) -> bool:
    domain = msg.from_address.rsplit("@", 1)[-1]
    return any(domain == d or domain.endswith("." + d) for d in ATS_DOMAINS)


def classify_by_rules(msg: MailMessage) -> Signal | None:
    """A confident stage, an explicit not-job-related, or None for 'ask the LLM'."""
    text = _haystack(msg)

    for pattern in NOT_A_RESPONSE:
        if re.search(pattern, text, re.IGNORECASE):
            return Signal(stage=None, company=None, title=None, confidence=0.9,
                          evidence="", job_related=False)

    for stage, patterns in STAGE_PATTERNS:
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # A calendar attachment corroborates an interview but never
                # establishes one on its own — automated footers carry them too.
                confidence = 0.95 if (stage != "interview" or msg.has_calendar_invite) else 0.85
                return Signal(
                    stage=stage,
                    company=_company_hint(msg),
                    title=None,
                    confidence=confidence,
                    evidence=_sentence_containing(text, match),
                    job_related=True,
                )
    return None


def _company_hint(msg: MailMessage) -> str | None:
    found = _COMPANY_FROM_SUBJECT.search(msg.subject)
    if found:
        return found.group(1).strip()
    domain = msg.from_address.rsplit("@", 1)[-1]
    if _from_ats(msg):
        return None          # the ATS domain names the vendor, not the employer
    return domain.split(".")[0].title() or None


# --- The LLM fallback -----------------------------------------------------

MIN_CONFIDENCE = 0.6

CLASSIFY_SYSTEM = """You read one email and decide what it says about a job application.

Reply with JSON only:
{"stage": one of "received" | "in_review" | "interview" | "offer" | "rejected" | null,
 "company": employer name or null,
 "title": job title or null,
 "confidence": 0.0-1.0,
 "evidence": the single sentence from the email that decided it,
 "job_related": true if this is a response to a job application the reader made}

Meanings:
- received: an automated acknowledgement that the application arrived.
- in_review: a human says the application is progressing or under consideration.
- interview: the reader is invited to talk, or asked to pick a time.
- offer: a job is being offered.
- rejected: the reader is not continuing in the process.

Set job_related to false for job-board newsletters, job alerts, and recruiter
cold outreach about roles the reader never applied to.

If the email does not clearly say any of these, return stage null with a low
confidence. Never guess: an invented stage is worse than no stage."""


class _LLMSignal(BaseModel):
    stage: str | None = None
    company: str | None = None
    title: str | None = None
    confidence: float = 0.0
    evidence: str = ""
    job_related: bool = True


UNRESOLVED = Signal(stage=None, company=None, title=None, confidence=0.0,
                    evidence="", job_related=True)


def classify(msg: MailMessage, llm: LLMClient | None) -> Signal:
    """Always returns a Signal. `stage is None` means we could not tell."""
    ruled = classify_by_rules(msg)
    if ruled is not None:
        return ruled
    if llm is None:
        return UNRESOLVED

    user = (f"From: {msg.from_address}\n"
            f"Subject: {msg.subject}\n\n"
            f"{msg.body[:4000]}")
    try:
        answer = llm.chat_json(MODEL_FAST, CLASSIFY_SYSTEM, user, _LLMSignal)
    except LLMError as exc:
        # Quota or outage. The mail stays unclassified and is retried next sync;
        # the alternative — guessing — is the one outcome we refuse.
        logger.warning("[inbox] classifier LLM unavailable: %s", exc)
        return UNRESOLVED

    if not answer.job_related:
        return Signal(stage=None, company=None, title=None,
                      confidence=answer.confidence, evidence="", job_related=False)

    valid = answer.stage in ("received", "in_review", "interview", "offer", "rejected")
    if not valid or answer.confidence < MIN_CONFIDENCE:
        return UNRESOLVED

    return Signal(stage=answer.stage, company=answer.company, title=answer.title,
                  confidence=answer.confidence, evidence=answer.evidence,
                  job_related=True)
