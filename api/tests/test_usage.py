import pytest
from fastapi import HTTPException

from app.services.usage import UsageStore, enforce_limit


def test_allows_up_to_limit():
    store = UsageStore()
    for _ in range(20):
        enforce_limit(store, "u1", limit=20)  # must not raise


def test_blocks_past_limit():
    store = UsageStore()
    for _ in range(20):
        enforce_limit(store, "u1", limit=20)
    with pytest.raises(HTTPException) as exc:
        enforce_limit(store, "u1", limit=20)
    assert exc.value.status_code == 429
    assert exc.value.detail == {"code": "DAILY_LIMIT_REACHED"}


def test_users_are_independent():
    store = UsageStore()
    for _ in range(20):
        enforce_limit(store, "u1", limit=20)
    enforce_limit(store, "u2", limit=20)  # different user, must not raise
