"""Deciding which application a mail belongs to.

Four steps, first hit wins. Step four is what makes the list complete rather
than merely accurate: an application made outside KRESUME appears the moment a
company replies to it.
"""
import re
import unicodedata
from dataclasses import dataclass

from tld import get_fld

from app.services.inbox_classify import Signal
from app.services.mailbox import ATS_DOMAINS, MailMessage

# Compared token by token after punctuation is stripped, so "A.Ş.", "AS" and
# "a.s." all collapse to the same thing. Matching on trailing substrings instead
# would mangle a company genuinely called "Sabancı".
LEGAL_TOKENS = frozenset({
    "as", "sti", "ltd", "limited", "sirketi", "anonim", "inc", "llc", "gmbh",
    "bv", "sa", "srl", "corp", "co", "company", "plc", "ag", "ab", "oy", "holding",
})

_TR_MAP = str.maketrans("ıİşŞğĞüÜöÖçÇ", "iIsSgGuUoOcC")


def normalize_company(raw: str | None) -> str:
    if not raw:
        return ""
    text = raw.translate(_TR_MAP)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    tokens = [re.sub(r"[^a-z0-9]+", "", token) for token in text.split()]
    tokens = [t for t in tokens if t]
    kept = [t for t in tokens if t not in LEGAL_TOKENS]
    # A company literally named "Holding" would otherwise normalize to nothing
    # and then match every other empty name.
    return "".join(kept or tokens)


def registrable_domain(value: str) -> str:
    """The registrable domain of a URL, bare host, or email address."""
    if "@" in value and "://" not in value:
        value = value.rsplit("@", 1)[-1]
    if "://" not in value:
        value = "https://" + value
    return (get_fld(value, fail_silently=True) or "").lower()


def _is_ats(domain: str) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in ATS_DOMAINS)


@dataclass(frozen=True)
class MatchResult:
    application: dict | None
    reason: str


def match_application(msg: MailMessage, signal: Signal, applications: list[dict],
                      threads: dict[str, str]) -> MatchResult:
    by_id = {a["id"]: a for a in applications}

    linked = threads.get(msg.thread_id)
    if linked and linked in by_id:
        return MatchResult(by_id[linked], "thread")

    sender_domain = registrable_domain(msg.from_address)
    # An ATS domain names the vendor, not the employer: two applications routed
    # through Greenhouse would otherwise collide into one.
    if sender_domain and not _is_ats(sender_domain):
        for app in applications:
            if registrable_domain(app.get("url") or "") == sender_domain:
                return MatchResult(app, "domain")

    wanted = normalize_company(signal.company)
    if wanted:
        for app in applications:
            if normalize_company(app.get("company")) == wanted:
                return MatchResult(app, "company")
        for app in applications:
            # The employer slug often sits in the ATS board URL:
            # boards.greenhouse.io/acme/jobs/1
            if wanted in re.sub(r"[^a-z0-9]+", "", (app.get("url") or "").casefold()):
                return MatchResult(app, "company")

    return MatchResult(None, "new")
