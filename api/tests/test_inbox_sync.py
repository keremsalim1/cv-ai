import pytest

from app.services.inbox_connect import ConnectionError_, encrypt_token
from app.services.inbox_sync import sync_user_inbox
from app.services.mailbox import FetchResult, MailMessage
from tests.test_inbox_connect import FakeDB, http_returning


class FakeSource:
    def __init__(self, result: FetchResult):
        self._result = result
        self.cursors: list[str | None] = []

    def fetch_new(self, cursor):
        self.cursors.append(cursor)
        return self._result


def mail(msg_id="m1", sender="no-reply@greenhouse.io", subject="Update",
         body="We have decided to move forward with other candidates.",
         thread="t1") -> MailMessage:
    return MailMessage(message_id=msg_id, thread_id=thread, from_address=sender,
                       subject=subject, received_at="2026-07-27T10:00:00+00:00",
                       body=body, has_calendar_invite=False)


class InboxDB(FakeDB):
    """FakeDB plus the per-table routing the sync needs.

    Keeps FakeDB's safety contract intact: the service role bypasses RLS, so
    every query must filter on user_id and may only touch that user's rows. A
    sync that forgets the filter fails here instead of reading another user's
    applications in production.
    """

    def __init__(self, connections=None, applications=None, events=None):
        super().__init__()
        self.tables = {
            "email_connections": list(connections or []),
            "applications": list(applications or []),
            "application_events": list(events or []),
        }

    def _owned(self, table, params) -> list[dict]:
        user_id = self._user_id(params)
        return [r for r in self.tables[table] if r.get("user_id") == user_id]

    def select(self, table, params):
        return list(self._owned(table, params))

    def insert(self, table, row, *, on_conflict=None):
        # Models `unique (user_id, message_id)` on application_events.
        if on_conflict and any(
            r.get("user_id") == row.get("user_id")
            and r.get("message_id") == row.get("message_id")
            for r in self.tables[table]
        ):
            return None
        self.inserted.append((table, row))
        stored = dict(row, id=row.get("id", f"{table}-{len(self.tables[table])}"))
        self.tables[table].append(stored)
        return stored

    def update(self, table, params, patch):
        self.updated.append((table, params, patch))
        target = params.get("id", "").removeprefix("eq.")
        matched = [r for r in self._owned(table, params)
                   if not target or r.get("id") == target]
        for row in matched:
            row.update(patch)
        return matched

    def delete(self, table, params):
        self._user_id(params)
        self.deleted.append((table, params))


def connected_db(**kwargs) -> InboxDB:
    return InboxDB(
        connections=[{"user_id": "u1", "refresh_token_enc": encrypt_token("1//rt"),
                      "last_history_id": "9100", "status": "active"}],
        **kwargs,
    )


def application_updates(db: InboxDB) -> list[tuple]:
    return [(params, patch) for table, params, patch in db.updated
            if table == "applications"]


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    from cryptography.fernet import Fernet
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("EMAIL_TOKEN_KEY", Fernet.generate_key().decode())
    yield
    get_settings.cache_clear()


def test_a_rejection_moves_a_matching_application_and_says_so():
    db = connected_db(applications=[
        {"id": "a1", "user_id": "u1",
         "url": "https://boards.greenhouse.io/acme/jobs/1",
         "company": "Acme", "stage": "received"},
    ])
    source = FakeSource(FetchResult([mail(subject="Your application to Acme")],
                                    cursor="9200", partial=False))

    report = sync_user_inbox(db, http_returning((200, {"access_token": "at"})),
                             None, "u1", source_factory=lambda *_: source)

    assert report.scanned == 1
    assert report.updated == [{"application_id": "a1", "company": "Acme",
                               "from_stage": "received", "to_stage": "rejected"}]
    params, patch = application_updates(db)[0]
    assert params == {"id": "eq.a1", "user_id": "eq.u1"}
    assert patch["stage"] == "rejected"


def test_every_processed_mail_is_recorded_even_when_nothing_moves():
    db = connected_db(applications=[
        {"id": "a1", "user_id": "u1", "url": "https://acme.com/j",
         "company": "Acme", "stage": "rejected"},
    ])
    source = FakeSource(FetchResult([mail(sender="hr@acme.com")],
                                    cursor="9200", partial=False))

    sync_user_inbox(db, http_returning((200, {"access_token": "at"})), None, "u1",
                    source_factory=lambda *_: source)

    events = [row for table, row in db.inserted if table == "application_events"]
    assert len(events) == 1
    assert events[0]["detected_stage"] == "rejected"
    assert events[0]["evidence"]
    assert application_updates(db) == []


def test_an_unmatched_mail_creates_an_external_application():
    db = connected_db()
    source = FakeSource(FetchResult(
        [mail(sender="hr@initech.com.tr", subject="Initech - başvurunuz",
              body="Başvurunuz olumsuz sonuçlanmıştır.")],
        cursor="9200", partial=False))

    report = sync_user_inbox(db, http_returning((200, {"access_token": "at"})),
                             None, "u1", source_factory=lambda *_: source)

    assert report.created == 1
    created = [row for table, row in db.inserted if table == "applications"][0]
    assert created["source"] == "email"
    assert created["status"] == "external"
    assert created["stage"] == "rejected"
    assert created["user_id"] == "u1"


def test_a_mail_the_classifier_cannot_read_creates_nothing():
    db = connected_db()
    source = FakeSource(FetchResult(
        [mail(sender="hr@initech.com.tr", subject="Bilgilendirme",
              body="Merhaba, kısa bir güncelleme.")],
        cursor="9200", partial=False))

    report = sync_user_inbox(db, http_returning((200, {"access_token": "at"})),
                             None, "u1", source_factory=lambda *_: source)

    assert report.created == 0
    assert report.updated == []
    assert [t for t, _ in db.inserted] == []   # not even an orphan event


def test_a_mail_that_is_not_job_related_is_skipped_entirely():
    db = connected_db()
    source = FakeSource(FetchResult(
        [mail(sender="jobs-noreply@linkedin.com", subject="30 new jobs",
              body="Here are this week's recommended jobs for you.")],
        cursor="9200", partial=False))

    report = sync_user_inbox(db, http_returning((200, {"access_token": "at"})),
                             None, "u1", source_factory=lambda *_: source)

    assert report.classified == 0
    assert db.inserted == []


def test_the_same_message_seen_twice_cannot_advance_a_stage_twice():
    db = connected_db(
        applications=[{"id": "a1", "user_id": "u1", "url": "https://acme.com/j",
                       "company": "Acme", "stage": "received"}],
        events=[{"user_id": "u1", "message_id": "m1", "thread_id": "t1",
                 "application_id": "a1"}],
    )
    source = FakeSource(FetchResult([mail(sender="hr@acme.com")],
                                    cursor="9200", partial=False))

    report = sync_user_inbox(db, http_returning((200, {"access_token": "at"})),
                             None, "u1", source_factory=lambda *_: source)

    assert report.updated == []
    assert report.scanned == 1


def test_the_cursor_and_sync_time_are_stored_after_a_clean_run():
    db = connected_db()
    source = FakeSource(FetchResult([], cursor="9200", partial=False))

    sync_user_inbox(db, http_returning((200, {"access_token": "at"})), None, "u1",
                    source_factory=lambda *_: source)

    patch = [p for table, _, p in db.updated if table == "email_connections"][0]
    assert patch["last_history_id"] == "9200"
    assert patch["last_synced_at"]


def test_a_partial_fetch_does_not_advance_the_cursor():
    db = connected_db()
    source = FakeSource(FetchResult([], cursor=None, partial=True))

    report = sync_user_inbox(db, http_returning((200, {"access_token": "at"})),
                             None, "u1", source_factory=lambda *_: source)

    assert report.partial is True
    patch = [p for table, _, p in db.updated if table == "email_connections"][0]
    assert "last_history_id" not in patch


def test_the_stored_cursor_is_handed_to_the_source():
    db = connected_db()
    source = FakeSource(FetchResult([], cursor="9200", partial=False))
    sync_user_inbox(db, http_returning((200, {"access_token": "at"})), None, "u1",
                    source_factory=lambda *_: source)
    assert source.cursors == ["9100"]


def test_a_user_without_a_connection_gets_an_empty_report_not_an_error():
    report = sync_user_inbox(InboxDB(), http_returning(), None, "u1",
                             source_factory=lambda *_: FakeSource(
                                 FetchResult([], cursor=None, partial=False)))

    assert report == type(report)()   # every field at its zero value


def test_a_revoked_grant_surfaces_instead_of_returning_an_empty_report():
    db = connected_db()
    with pytest.raises(ConnectionError_):
        sync_user_inbox(db, http_returning((400, {"error": "invalid_grant"})),
                        None, "u1", source_factory=lambda *_: FakeSource(
                            FetchResult([], cursor=None, partial=False)))
