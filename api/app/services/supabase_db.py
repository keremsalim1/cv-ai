"""Server-side database access, used only by the inbox feature.

Everything else in this product reaches Supabase from the browser under RLS
(see web/src/lib/db.ts). The inbox cannot: it stores a Gmail refresh token that
no browser may read, so no RLS policy can exist for it. That forces the service
role, which bypasses RLS — so every caller here must filter on user_id itself.
"""
import httpx

from app.config import get_settings


class SupabaseDB:
    def __init__(self, client: httpx.Client, url: str, key: str) -> None:
        self._client = client
        self._base = url.rstrip("/") + "/rest/v1/"
        self._headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def _send(self, method: str, table: str, *, params=None, json=None,
              prefer: str | None = None) -> list[dict]:
        headers = dict(self._headers)
        if prefer:
            headers["Prefer"] = prefer
        resp = self._client.request(
            method, self._base + table, params=params, json=json, headers=headers,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"supabase {method} {table} failed: {resp.text}")
        if not resp.content:
            return []
        body = resp.json()
        return body if isinstance(body, list) else [body]

    def select(self, table: str, params: dict[str, str]) -> list[dict]:
        return self._send("GET", table, params=params)

    def insert(self, table: str, row: dict, *,
               on_conflict: str | None = None) -> dict | None:
        params = {"on_conflict": on_conflict} if on_conflict else None
        prefer = "return=representation"
        if on_conflict:
            prefer += ",resolution=ignore-duplicates"
        rows = self._send("POST", table, params=params, json=row, prefer=prefer)
        return rows[0] if rows else None

    def update(self, table: str, params: dict[str, str], patch: dict) -> list[dict]:
        return self._send("PATCH", table, params=params, json=patch,
                          prefer="return=representation")

    def delete(self, table: str, params: dict[str, str]) -> None:
        self._send("DELETE", table, params=params)


def get_db() -> SupabaseDB:
    settings = get_settings()
    return SupabaseDB(httpx.Client(timeout=20.0),
                      settings.supabase_url, settings.supabase_service_key)
