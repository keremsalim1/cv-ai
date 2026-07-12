from pydantic import BaseModel, ValidationError

from app.config import get_settings

MODEL_FAST = "gpt-4o-mini"
MODEL_SMART = "gpt-4o"


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

    # OpenAI() rejects an empty api_key at construction; fall back to a
    # placeholder so the app boots without a key (calls then fail with 401).
    return LLMClient(OpenAI(api_key=get_settings().openai_api_key or "missing-api-key"))
