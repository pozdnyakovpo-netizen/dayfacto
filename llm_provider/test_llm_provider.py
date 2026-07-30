"""Юнит-тесты слоя (сеть не требуется): pytest llm_provider/test_llm_provider.py"""

import pytest

from .base import (
    BaseProvider, LLMParseError, LLMRequest, LLMTransientError,
)
from .json_utils import extract_json, validate_schema
from .router import LLMRouter

SCHEMA = {
    "type": "object",
    "required": ["headline", "body"],
    "properties": {"headline": {"type": "string"}, "hashtags": {"type": "array"}},
}


# --- разбор JSON ------------------------------------------------------------
@pytest.mark.parametrize("raw", [
    '{"headline": "A", "body": "B"}',
    '```json\n{"headline": "A", "body": "B"}\n```',
    'Конечно! Вот результат:\n{"headline": "A", "body": "B"}\nГотово.',
    '{"headline": "A", "body": "B",}',
    '{"headline": "A {не скобка}", "body": "B"}',
])
def test_extract_json_variants(raw):
    assert extract_json(raw)["headline"].startswith("A")


def test_extract_json_fails_loudly():
    with pytest.raises(LLMParseError):
        extract_json("Извините, не могу помочь.")


def test_schema_required_and_types():
    validate_schema({"headline": "A", "body": "B"}, SCHEMA)
    with pytest.raises(LLMParseError):
        validate_schema({"headline": "A"}, SCHEMA)
    with pytest.raises(LLMParseError):
        validate_schema({"headline": 1, "body": "B"}, SCHEMA)


# --- retry и фолбэк ---------------------------------------------------------
class FlakyProvider(BaseProvider):
    name = "flaky"
    model = "flaky-1"

    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.calls = 0

    def _complete(self, req: LLMRequest):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise LLMTransientError("503")
        return '{"headline": "A", "body": "B"}', 10, 20


def test_retry_recovers(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    p = FlakyProvider(fail_times=2)
    resp = p.generate(LLMRequest(system="s", user="u", json_schema=SCHEMA))
    assert resp.attempts == 3 and resp.data["headline"] == "A"


def test_router_falls_back(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    dead, alive = FlakyProvider(fail_times=99), FlakyProvider(fail_times=0)
    alive.name = "alive"
    router = LLMRouter({"dead": dead, "alive": alive}, default="dead")
    resp = router.generate("editorial", LLMRequest(system="s", user="u", json_schema=SCHEMA))
    assert resp.provider == "alive"
