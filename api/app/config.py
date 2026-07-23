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

    # Persistent Chromium profile for /apply: user logins on job sites survive
    # between prepare/submit calls. Never stores passwords ourselves.
    browser_profile_dir: str = ".browser-profile"

    model_config = {"env_file": ".env"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
