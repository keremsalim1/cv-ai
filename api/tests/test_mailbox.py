import httpx
import pytest

from app.services.mailbox import GmailSource, build_query
from tests.fake_gmail import FakeGmail, message, part


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


def test_a_quota_error_on_the_list_call_returns_an_empty_partial_result():
    gmail = FakeGmail([message("m1")], quota_on=frozenset({"list"}))
    result = GmailSource(gmail.client(), "at").fetch_new(None)

    assert result.messages == []
    assert result.partial is True
    assert result.cursor is None


def test_a_quota_error_on_history_does_not_fall_back_to_a_full_scan():
    gmail = FakeGmail([message("m1")], quota_on=frozenset({"history"}))
    result = GmailSource(gmail.client(), "at").fetch_new("9100")

    assert result.messages == []
    assert result.partial is True
    assert result.cursor is None
    # a quota error is not an expired cursor: it must not trigger the
    # full-scan fallback, which would just hit the same quota again.
    assert not any(r.url.path.endswith("/messages") for r in gmail.requests)


def test_a_quota_error_on_the_profile_call_still_returns_fetched_messages():
    gmail = FakeGmail([message("m1")], quota_on=frozenset({"profile"}))
    result = GmailSource(gmail.client(), "at").fetch_new(None)

    assert [m.message_id for m in result.messages] == ["m1"]
    assert result.partial is True
    assert result.cursor is None


# --- Pagination ---------------------------------------------------------

def test_pagination_across_pages_of_the_message_listing():
    gmail = FakeGmail([message("m1"), message("m2")], list_pages=[["m1"], ["m2"]])
    result = GmailSource(gmail.client(), "at").fetch_new(None)

    assert sorted(m.message_id for m in result.messages) == ["m1", "m2"]
    assert result.partial is False
    assert result.cursor == "9100"


def test_a_quota_error_on_the_second_listing_page_keeps_the_first_pages_messages():
    gmail = FakeGmail([message("m1"), message("m2")], list_pages=[["m1"], ["m2"]],
                       list_quota_on_page=1)
    result = GmailSource(gmail.client(), "at").fetch_new(None)

    assert [m.message_id for m in result.messages] == ["m1"]
    assert result.partial is True
    assert result.cursor is None


def test_history_pagination_only_advances_the_cursor_after_the_last_page():
    pages = [
        {"history": [{"messagesAdded": [{"message": {"id": "m1", "threadId": "t1"}}]}],
         "historyId": "9400"},
        {"history": [{"messagesAdded": [{"message": {"id": "m2", "threadId": "t1"}}]}],
         "historyId": "9400"},
    ]
    gmail = FakeGmail([message("m1"), message("m2")], history_pages=pages)
    result = GmailSource(gmail.client(), "at").fetch_new("9100")

    assert sorted(m.message_id for m in result.messages) == ["m1", "m2"]
    assert result.cursor == "9400"
    assert result.partial is False


def test_pagination_is_capped_to_avoid_an_infinite_loop():
    # A server that keeps handing back a token must not hang the sync.
    pages = [[f"m{i}"] for i in range(60)]
    msgs = [message(f"m{i}") for i in range(60)]
    gmail = FakeGmail(msgs, list_pages=pages)
    result = GmailSource(gmail.client(), "at").fetch_new(None)

    assert len(result.messages) == 50   # the cap, not all 60
    assert result.partial is True
    assert result.cursor is None


# --- One bad message must not sink the batch -----------------------------

def test_a_message_that_404s_mid_batch_is_skipped_not_fatal():
    gmail = FakeGmail([message("m1"), message("m2")], list_pages=[["m1", "ghost", "m2"]])
    result = GmailSource(gmail.client(), "at").fetch_new(None)

    assert [m.message_id for m in result.messages] == ["m1", "m2"]
    assert result.partial is False


def test_a_message_with_corrupt_base64_is_skipped_not_fatal():
    corrupt = [{"mimeType": "text/plain", "body": {"data": "bad"}}]
    gmail = FakeGmail([message("m1"), message("m2", parts=corrupt), message("m3")])
    result = GmailSource(gmail.client(), "at").fetch_new(None)

    assert [m.message_id for m in result.messages] == ["m1", "m3"]
    assert result.partial is False


def test_a_history_entry_without_a_message_id_is_skipped_not_fatal():
    gmail = FakeGmail(
        [message("m1")],
        history={"historyId": "9200",
                 "history": [{"messagesAdded": [
                     {"message": {"threadId": "t1"}},               # no id — must not KeyError
                     {"message": {"id": "m1", "threadId": "t1"}},
                 ]}]},
    )
    result = GmailSource(gmail.client(), "9100").fetch_new("9100")

    assert [m.message_id for m in result.messages] == ["m1"]
    assert result.cursor == "9200"


# --- Body extraction ------------------------------------------------------

def test_body_extraction_finds_text_plain_nested_in_multipart():
    nested = [part("multipart/alternative", parts=[
        part("text/plain", data="Merhaba Ada, plain"),
        part("text/html", data="<p>Merhaba <b>Ada</b>, html</p>"),
    ])]
    gmail = FakeGmail([message("m1", parts=nested)])
    msg = GmailSource(gmail.client(), "at").fetch_new(None).messages[0]

    assert msg.body == "Merhaba Ada, plain"


def test_body_extraction_falls_back_to_html_when_no_plain_text_exists():
    html_only = [part("text/html", data="<p>Hello <b>Ada</b>, welcome</p>")]
    gmail = FakeGmail([message("m1", parts=html_only)])
    msg = GmailSource(gmail.client(), "at").fetch_new(None).messages[0]

    assert "Hello" in msg.body
    assert "Ada" in msg.body
    assert "<p>" not in msg.body
    assert "<b>" not in msg.body


def test_body_extraction_handles_a_non_multipart_message():
    gmail = FakeGmail([message("m1", multipart=False, body="Plain body, no parts at all")])
    msg = GmailSource(gmail.client(), "at").fetch_new(None).messages[0]

    assert msg.body == "Plain body, no parts at all"


def test_a_calendar_part_nested_one_level_deep_is_still_flagged():
    nested = [
        part("text/plain", data="hi"),
        part("multipart/mixed", parts=[
            part("text/calendar", data="BEGIN:VCALENDAR"),
        ]),
    ]
    gmail = FakeGmail([message("m1", parts=nested)])
    assert GmailSource(gmail.client(), "at").fetch_new(None).messages[0].has_calendar_invite


# --- 403-shaped quota errors -----------------------------------------------

def test_a_403_with_a_quota_reason_is_treated_as_a_quota_error():
    gmail = FakeGmail([message("m1")], quota_on=frozenset({"list"}), quota_via_403=True)
    result = GmailSource(gmail.client(), "at").fetch_new(None)

    assert result.messages == []
    assert result.partial is True
    assert result.cursor is None


def test_a_403_without_a_recognized_quota_reason_is_a_real_error():
    gmail = FakeGmail([message("m1")], quota_on=frozenset({"list"}), quota_via_403=True,
                       quota_reason="insufficientPermissions")

    with pytest.raises(httpx.HTTPError):
        GmailSource(gmail.client(), "at").fetch_new(None)


# --- HTML bodies must not leak markup-only text ---------------------------

def test_style_and_script_text_never_reaches_the_body():
    # Real ATS templates ship a <style> block (and often a tracking script).
    # lxml's text_content() would otherwise hand the classifier a body that
    # starts with CSS.
    html = (
        "<html><head><style>.btn { color: #ff0000; font-size: 14px; }</style>"
        "<script>var trackId = 'abc123';</script></head>"
        "<body><p>Merhaba Ada, başvurunuz alındı.</p></body></html>"
    )
    gmail = FakeGmail([message("m1", parts=[part("text/html", data=html)])])
    body = GmailSource(gmail.client(), "at").fetch_new(None).messages[0].body

    assert body == "Merhaba Ada, başvurunuz alındı."
    assert "color" not in body
    assert "trackId" not in body


# --- Transient (non-quota) failures must not discard work -----------------

def test_a_transient_error_on_the_profile_call_still_returns_fetched_messages():
    # Same reasoning as the quota case: the messages are already in hand.
    gmail = FakeGmail([message("m1")], profile_status=500)
    result = GmailSource(gmail.client(), "at").fetch_new(None)

    assert [m.message_id for m in result.messages] == ["m1"]
    assert result.partial is True
    assert result.cursor is None


def test_a_transient_error_on_a_later_listing_page_keeps_the_first_pages_messages():
    gmail = FakeGmail([message("m1"), message("m2")], list_pages=[["m1"], ["m2"]],
                       list_error_on_page=1)
    result = GmailSource(gmail.client(), "at").fetch_new(None)

    assert [m.message_id for m in result.messages] == ["m1"]
    assert result.partial is True
    assert result.cursor is None


def test_a_transient_error_on_the_first_listing_page_surfaces_as_an_error():
    # Nothing was gathered, so there is no work to protect — and a real
    # failure (bad scope, dead token) must not be disguised as "no new mail".
    gmail = FakeGmail([message("m1")], list_pages=[["m1"]], list_error_on_page=0)

    with pytest.raises(httpx.HTTPError):
        GmailSource(gmail.client(), "at").fetch_new(None)


def test_a_transient_error_on_a_later_history_page_does_not_trigger_a_full_scan():
    pages = [
        {"history": [{"messagesAdded": [{"message": {"id": "m1", "threadId": "t1"}}]}],
         "historyId": "9400"},
        {"history": [{"messagesAdded": [{"message": {"id": "m2", "threadId": "t1"}}]}],
         "historyId": "9400"},
    ]
    gmail = FakeGmail([message("m1"), message("m2")], history_pages=pages,
                       history_error_on_page=1)
    result = GmailSource(gmail.client(), "at").fetch_new("9100")

    assert [m.message_id for m in result.messages] == ["m1"]
    assert result.partial is True
    assert result.cursor is None
    # a mid-pagination failure is not an expired cursor: re-listing the whole
    # mailbox would be wasted work, and the cursor is still valid.
    assert not any(r.url.path.endswith("/messages") for r in gmail.requests)
