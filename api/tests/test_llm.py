import pytest
from pydantic import BaseModel

from app.services.llm import MODEL_FAST, LLMClient, LLMError
from tests.conftest import FakeOpenAI


class Point(BaseModel):
    x: int
    y: int


def test_valid_json_parsed():
    fake = FakeOpenAI(['{"x": 1, "y": 2}'])
    result = LLMClient(fake).chat_json(MODEL_FAST, "sys", "user", Point)
    assert result == Point(x=1, y=2)
    assert fake.calls[0]["model"] == MODEL_FAST
    assert fake.calls[0]["response_format"] == {"type": "json_object"}


def test_retry_once_on_bad_json():
    fake = FakeOpenAI(["not json", '{"x": 1, "y": 2}'])
    result = LLMClient(fake).chat_json(MODEL_FAST, "sys", "user", Point)
    assert result == Point(x=1, y=2)
    assert len(fake.calls) == 2


def test_raises_after_two_bad():
    fake = FakeOpenAI(["nope", "still nope"])
    with pytest.raises(LLMError):
        LLMClient(fake).chat_json(MODEL_FAST, "sys", "user", Point)
