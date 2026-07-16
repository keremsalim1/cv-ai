from pydantic import BaseModel, ValidationError

from app.config import get_settings

_settings = get_settings()

# Google Gemini models, served through the OpenAI-compatible endpoint.
MODEL_FAST = _settings.gemini_model_fast
MODEL_SMART = _settings.gemini_model_smart


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, client):
        self._client = client

    def chat_json(self, model: str, system: str, user: str,
                  schema: type[BaseModel]) -> BaseModel:
        for _attempt in range(2):
            resp = self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
            content = resp.choices[0].message.content
            try:
                return schema.model_validate_json(content)
            except ValidationError:
                continue
        raise LLMError("LLM returned invalid JSON twice")


def get_llm() -> LLMClient:
    from openai import OpenAI

    # Gemini's OpenAI-compatible endpoint: same SDK, Google's models. OpenAI()
    # rejects an empty api_key at construction; fall back to a placeholder so the
    # app boots without a key (calls then fail with 401).
    settings = get_settings()
    return LLMClient(
        OpenAI(
            api_key=settings.gemini_api_key or "missing-api-key",
            base_url=settings.gemini_base_url,
        )
    )
