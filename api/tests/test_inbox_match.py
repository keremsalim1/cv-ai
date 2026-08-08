from app.services.inbox_classify import Signal
from app.services.inbox_match import (
    match_application, normalize_company, registrable_domain,
)
from app.services.mailbox import MailMessage


def mail(sender="hr@acme.com", thread="t1") -> MailMessage:
    return MailMessage(message_id="m1", thread_id=thread, from_address=sender,
                       subject="s", received_at=None, body="b",
                       has_calendar_invite=False)


def signal(company=None) -> Signal:
    return Signal(stage="rejected", company=company, title=None, confidence=0.9,
                  evidence="e", job_related=True)


def test_legal_suffixes_and_case_do_not_distinguish_companies():
    assert normalize_company("Acme A.Ş.") == normalize_company("ACME Inc.")
    assert normalize_company("Initech Ltd. Şti.") == normalize_company("initech")
    assert normalize_company("Globex GmbH") == normalize_company("Globex B.V.")


def test_turkish_characters_normalize_consistently():
    assert normalize_company("Öztürk Yazılım") == normalize_company("ozturk yazilim")


def test_normalizing_nothing_is_an_empty_string_not_a_crash():
    assert normalize_company(None) == ""


def test_the_registrable_domain_ignores_subdomains_and_schemes():
    assert registrable_domain("https://acme.wd3.myworkdayjobs.com/job/1") == "myworkdayjobs.com"
    assert registrable_domain("careers.acme.co.uk") == "acme.co.uk"
    assert registrable_domain("hr@acme.com") == "acme.com"


def test_a_known_thread_wins_over_everything_else():
    apps = [{"id": "a1", "url": "https://other.com/j", "company": "Other"},
            {"id": "a2", "url": "https://acme.com/j", "company": "Acme"}]
    result = match_application(mail(thread="t9"), signal("Acme"), apps, {"t9": "a1"})
    assert result.application["id"] == "a1"
    assert result.reason == "thread"


def test_the_sender_domain_matches_the_application_url():
    apps = [{"id": "a1", "url": "https://careers.acme.com/jobs/5", "company": None}]
    result = match_application(mail("no-reply@acme.com"), signal(), apps, {})
    assert result.application["id"] == "a1"
    assert result.reason == "domain"


def test_an_ats_sender_domain_does_not_match_an_unrelated_application():
    # Two applications both routed through Greenhouse must not collide.
    apps = [{"id": "a1", "url": "https://boards.greenhouse.io/globex/jobs/1",
             "company": "Globex"}]
    result = match_application(mail("no-reply@greenhouse.io"), signal("Acme"), apps, {})
    assert result.application is None
    assert result.reason == "new"


def test_the_company_name_matches_when_the_domain_cannot():
    apps = [{"id": "a1", "url": "https://boards.greenhouse.io/acme/jobs/1",
             "company": "Acme A.Ş."}]
    result = match_application(mail("no-reply@greenhouse.io"), signal("ACME Inc."), apps, {})
    assert result.application["id"] == "a1"
    assert result.reason == "company"


def test_no_match_asks_for_a_new_application():
    result = match_application(mail("hr@unknown.example"), signal("Unknown"), [], {})
    assert result.application is None
    assert result.reason == "new"


def test_a_blank_company_never_matches_an_application_with_a_blank_company():
    # Both empty must not be treated as equal, or every unmatched mail collides.
    apps = [{"id": "a1", "url": "https://x.example/j", "company": None}]
    result = match_application(mail("hr@other.example"), signal(None), apps, {})
    assert result.application is None
