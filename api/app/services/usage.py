from collections import defaultdict
from datetime import date

from fastapi import Depends, HTTPException

from app.auth import get_current_user
from app.config import get_settings


class UsageStore:
    """In-memory daily counter. Swap for a DB-backed store in Plan 2."""

    def __init__(self):
        self._counts: dict[tuple[str, str], int] = defaultdict(int)

    def increment(self, user_id: str) -> int:
        key = (user_id, date.today().isoformat())
        self._counts[key] += 1
        return self._counts[key]


usage_store = UsageStore()


def enforce_limit(store: UsageStore, user_id: str, limit: int) -> None:
    if store.increment(user_id) > limit:
        raise HTTPException(status_code=429, detail={"code": "DAILY_LIMIT_REACHED"})


def check_usage(user_id: str = Depends(get_current_user)) -> str:
    enforce_limit(usage_store, user_id, get_settings().daily_ai_limit)
    return user_id
