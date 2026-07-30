"""Базовый интерфейс LLM-провайдера.

Всё, что ниже по пайплайну (editorial, critique, ranking), знает ТОЛЬКО про
этот интерфейс. Добавление новой модели = новый файл *_provider.py + строка
в конфиге router. Ноль изменений в остальном пайплайне.
"""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


# --------------------------------------------------------------------------
# Исключения
# --------------------------------------------------------------------------
class LLMError(Exception):
    """Базовая ошибка слоя."""


class LLMTransientError(LLMError):
    """Временная (429/5xx/таймаут) — можно и нужно ретраить."""


class LLMPermanentError(LLMError):
    """Постоянная (401/400/невалидный конфиг) — ретрай бесполезен."""


class LLMParseError(LLMError):
    """Модель вернула не то, что мы просили (невалидный JSON/схема)."""

    def __init__(self, message: str, raw: str = ""):
        super().__init__(message)
        self.raw = raw


# --------------------------------------------------------------------------
# Контракты
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class LLMRequest:
    system: str
    user: str
    max_tokens: int = 1500
    temperature: float = 0.3
    # Если задана — ответ обязан быть JSON и пройти валидацию по схеме.
    json_schema: Mapping[str, Any] | None = None
    # Свободные метаданные для логирования/аудита (story_id, draft_id, task).
    meta: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    text: str
    data: dict[str, Any] | None       # распарсенный JSON, если запрашивался
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    attempts: int = 1

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class BaseProvider(abc.ABC):
    """Каждый конкретный провайдер реализует только _complete()."""

    name: str = "base"
    model: str = ""

    # --- то, что реализует наследник ---------------------------------------
    @abc.abstractmethod
    def _complete(self, req: LLMRequest) -> tuple[str, int, int]:
        """Вернуть (text, prompt_tokens, completion_tokens).

        Должен поднимать LLMTransientError / LLMPermanentError.
        """

    def health(self) -> bool:
        """Дешёвая проверка живости — используется decision/alerts."""
        try:
            self._complete(LLMRequest(system="ping", user="ping", max_tokens=8))
            return True
        except LLMError:
            return False

    # --- общая для всех логика ---------------------------------------------
    def generate(self, req: LLMRequest) -> LLMResponse:
        from .json_utils import extract_json, validate_schema
        from .retry import call_with_retry

        started = time.monotonic()
        text, pt, ct, attempts = call_with_retry(self._complete, req)

        data = None
        if req.json_schema is not None:
            data = extract_json(text)          # поднимет LLMParseError
            validate_schema(data, req.json_schema)

        return LLMResponse(
            text=text,
            data=data,
            provider=self.name,
            model=self.model,
            prompt_tokens=pt,
            completion_tokens=ct,
            latency_ms=int((time.monotonic() - started) * 1000),
            attempts=attempts,
        )

    def critique(self, req: LLMRequest) -> LLMResponse:
        """Семантически отдельная задача — отдельный метод, чтобы router мог
        направить критику на другого провайдера, чем редактуру."""
        return self.generate(req)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.__class__.__name__} model={self.model!r}>"


ProviderRegistry = dict[str, BaseProvider]
__all__: Sequence[str] = (
    "BaseProvider", "LLMRequest", "LLMResponse",
    "LLMError", "LLMTransientError", "LLMPermanentError", "LLMParseError",
)
