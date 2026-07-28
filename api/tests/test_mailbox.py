from app.services.mailbox import GmailSource, build_query
from tests.fake_gmail import FakeGmail, message


def test_the_query_narrows_on_ats_senders_and_application_words():
    q = build_query(days=90)
    assert "newer_than:90d" in q
    assert "greenhouse.io" in q
    assert "myworkdayjobs.com" in q or "myworkday.com" in q
    assert "başvuru" in q
    assert "interview" in q


def test_a_first_sync_lists_messages_and_returns_a_cursor():
    gmail = FakeGmail([message("m1", subject="Application received")])
    result = GmailSource(gmail.client(), "at").fetch_new(None)

    assert [m.message_id for m in result.messages] == ["m1"]
    assert result.cursor == "9100"      # from users/me/profile
    assert result.partial is False


def test_a_message_carries_its_headers_and_decoded_body():
    gmail = FakeGmail([message("m1", sender="Acme HR <hr@acme.com>",
                                subject="Görüşme daveti", body="Merhaba Ada")])
    msg = GmailSource(gmail.client(), "at").fetch_new(None).messages[0]

    assert msg.from_address == "hr@acme.com"     # display name stripped
    assert msg.subject == "Görüşme daveti"
    assert msg.body == "Merhaba Ada"
    assert msg.thread_id == "t1"
    assert msg.received_at.startswith("2026-07-27")


def test_a_calendar_attachment_is_flagged():
    gmail = FakeGmail([message("m1", calendar=True)])
    assert GmailSource(gmail.client(), "at").fetch_new(None).messages[0].has_calendar_invite


def test_an_incremental_sync_only_fetches_what_history_reports():
    gmail = FakeGmail(
        [message("m1"), message("m2")],
        history={"historyId": "9200",
                 "history": [{"messagesAdded": [{"message": {"id": "m2", "threadId": "t1"}}]}]},
    )
    result = GmailSource(gmail.client(), "9100").fetch_new("9100")

    assert [m.message_id for m in result.messages] == ["m2"]
    assert result.cursor == "9200"


def test_an_expired_cursor_falls_back_to_a_full_query_scan():
    # Gmail keeps history for about a week; a stale cursor 404s.
    gmail = FakeGmail([message("m1")], history_status=404)
    result = GmailSource(gmail.client(), "at-old").fetch_new("1")

    assert [m.message_id for m in result.messages] == ["m1"]
    assert result.partial is False


def test_a_quota_error_returns_what_was_read_and_says_it_is_partial():
    gmail = FakeGmail([message("m1"), message("m2"), message("m3")], quota_after=1)
    result = GmailSource(gmail.client(), "at").fetch_new(None)

    assert len(result.messages) == 1
    assert result.partial is True
    # the cursor must not advance past unread mail
    assert result.cursor is None


def test_history_with_no_new_messages_returns_nothing_and_advances_the_cursor():
    gmail = FakeGmail([message("m1")], history={"historyId": "9300"})
    result = GmailSource(gmail.client(), "at").fetch_new("9100")

    assert result.messages == []
    assert result.cursor == "9300"
