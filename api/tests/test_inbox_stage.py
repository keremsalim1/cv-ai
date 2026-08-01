import pytest

from app.services.inbox_stage import next_stage


@pytest.mark.parametrize("current,detected,expected", [
    ("received", "in_review", "in_review"),
    ("received", "interview", "interview"),
    ("in_review", "offer", "offer"),
    ("received", "rejected", "rejected"),
    ("interview", "rejected", "rejected"),
])
def test_a_later_stage_moves_the_application_forward(current, detected, expected):
    assert next_stage(current, detected) == expected


@pytest.mark.parametrize("current,detected", [
    ("interview", "received"),
    ("offer", "in_review"),
    ("in_review", "received"),
])
def test_a_delayed_earlier_mail_does_not_rewind_the_badge(current, detected):
    # Mail arrival order is not event order: an auto-acknowledgement can land
    # after an interview invitation.
    assert next_stage(current, detected) is None


def test_the_same_stage_twice_changes_nothing():
    assert next_stage("interview", "interview") is None


def test_rejection_is_terminal():
    for detected in ("received", "in_review", "interview", "offer"):
        assert next_stage("rejected", detected) is None


def test_an_unresolved_classification_changes_nothing():
    assert next_stage("received", None) is None


def test_an_application_with_no_stage_yet_takes_whatever_arrives():
    assert next_stage(None, "interview") == "interview"


def test_an_unknown_stage_string_is_refused_rather_than_stored():
    assert next_stage("received", "hired") is None
