from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Gemini via its OpenAI-compatible endpoint — same `openai` SDK, Google's models.
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    # Fast = structured extraction (CV parse, job criteria) — high volume, easy,
    # so a lighter model conserves quota. Smart = reasoning & Turkish-quality-
    # critical work (scoring, ATS rewrite) — the strongest model available on the
    # free tier. Both verified working on a free key (pro models return 429/no
    # free quota); override via env if Google rotates these preview IDs.
    gemini_model_fast: str = "gemini-3.1-flash-lite-preview"
    gemini_model_smart: str = "gemini-3-flash-preview"

    # Modern Supabase projects sign access tokens asymmetrically (ES256); the
    # API verifies them against the project's public JWKS endpoint. The HS256
    # shared secret remains as a fallback for legacy projects and the test suite.
    supabase_jwks_url: str = ""
    supabase_jwt_secret: str = "insecure-test-secret-change-in-prod-0123456789"
    daily_ai_limit: int = 20

    # The inbox feature is the only server-side database consumer. It needs the
    # service role because the Gmail refresh token must be unreadable by any
    # browser, which means no RLS policy can grant access to it. Every query
    # this key issues filters on user_id explicitly — see supabase_db callers.
    supabase_url: str = ""
    supabase_service_key: str = ""

    # Base dir for persistent Chromium profiles; each user gets their own
    # subdirectory (see browser.profile_dir_for) so their logins on job sites
    # survive between calls without ever being visible to another user. We never
    # store passwords ourselves.
    browser_profile_dir: str = ".browser-profile"
    # Each assisted-apply browser costs ~300-500MB, so the box can only host a
    # handful at once. Raise it only alongside the RAM to back it.
    max_browser_sessions: int = 4

    model_config = {"env_file": ".env"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
