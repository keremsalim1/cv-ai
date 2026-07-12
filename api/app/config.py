from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = ""
    supabase_jwt_secret: str = "test-secret-change-in-prod"
    daily_ai_limit: int = 20

    model_config = {"env_file": ".env"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
