"""Роутер провайдеров.

Кто именно обрабатывает задачу — решается по task ("editorial", "critique",
"cluster_similarity", "topic_classify"), значение берётся из system_config
(hot-reload, TTL 30с) с фолбэком на переменные окружения.

Если основной провайдер лёг — автоматический фолбэк на резервный, событие
пишется в лог и должно уходить алертом админу (Блок 15.3).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Callable

from .base import (
    BaseProvider, LLMError, LLMParseError, LLMRequest, LLMResponse,
)

log = logging.getLogger("llm_provider.router")

CONFIG_TTL = 30.0  # сек


class LLMRouter:
    def __init__(
        self,
        providers: dict[str, BaseProvider],
        config_reader: Callable[[str], str | None] | None = None,
        default: str | None = None,
    ):
        if not providers:
            raise ValueError("Нужен хотя бы один провайдер")
        self.providers = providers
        self._read_config = config_reader or (lambda key: None)
        self.default = default or os.environ.get(
            "LLM_PROVIDER_DEFAULT", next(iter(providers))
        )
        self._cache: dict[str, tuple[float, str]] = {}

    # ------------------------------------------------------------------
    def _resolve(self, task: str) -> BaseProvider:
        now = time.monotonic()
        cached = self._cache.get(task)
        if cached and now - cached[0] < CONFIG_TTL:
            name = cached[1]
        else:
            name = (
                self._read_config(f"llm_provider.{task}")
                or os.environ.get(f"LLM_PROVIDER_{task.upper()}")
                or self.default
            )
            self._cache[task] = (now, name)

        if name not in self.providers:
            log.error("Провайдер %r для задачи %r не зарегистрирован, беру default", name, task)
            name = self.default
        return self.providers[name]

    def _fallbacks(self, primary: BaseProvider) -> list[BaseProvider]:
        return [p for n, p in self.providers.items() if p is not primary]

    # ------------------------------------------------------------------
    def run(self, task: str, req: LLMRequest, *, critique: bool = False) -> LLMResponse:
        primary = self._resolve(task)
        chain = [primary] + self._fallbacks(primary)
        last: Exception | None = None

        for idx, provider in enumerate(chain):
            method = provider.critique if critique else provider.generate
            try:
                resp = method(req)
                if idx > 0:
                    log.warning(
                        "task=%s: сработал фолбэк на %s (основной %s недоступен)",
                        task, provider.name, primary.name,
                    )
                log.info(
                    "task=%s provider=%s tokens=%s latency=%sms attempts=%s meta=%s",
                    task, provider.name, resp.total_tokens,
                    resp.latency_ms, resp.attempts, dict(req.meta),
                )
                return resp
            except LLMParseError as exc:
                # Схема не сошлась — смена провайдера не поможет, это дело
                # вызывающего сервиса (retry с уточняющим промптом → модерация).
                log.warning("task=%s provider=%s: невалидный JSON", task, provider.name)
                raise exc
            except LLMError as exc:
                last = exc
                log.error("task=%s provider=%s упал: %s", task, provider.name, exc)

        raise LLMError(f"Все провайдеры недоступны для task={task}: {last}") from last

    # Удобные обёртки для сервисов
    def generate(self, task: str, req: LLMRequest) -> LLMResponse:
        return self.run(task, req)

    def critique(self, req: LLMRequest) -> LLMResponse:
        return self.run("critique", req, critique=True)

    def health(self) -> dict[str, bool]:
        return {name: p.health() for name, p in self.providers.items()}


# ----------------------------------------------------------------------
def build_default_router(config_reader: Callable[[str], str | None] | None = None) -> LLMRouter:
    """Собирает роутер из того, что реально сконфигурировано в окружении."""
    providers: dict[str, BaseProvider] = {}

    if os.environ.get("GIGACHAT_AUTH_KEY"):
        from .gigachat_provider import GigaChatProvider
        providers["gigachat"] = GigaChatProvider(
            model=os.environ.get("GIGACHAT_MODEL", "GigaChat-Pro"),
            verify_ssl=os.environ.get("GIGACHAT_CA_BUNDLE") or True,
        )

    if os.environ.get("ANTHROPIC_API_KEY"):
        from .claude_provider import ClaudeProvider
        providers["claude"] = ClaudeProvider(
            model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5"),
        )

    if not providers:
        raise RuntimeError("Не задан ни один ключ провайдера (GIGACHAT_AUTH_KEY / ANTHROPIC_API_KEY)")

    return LLMRouter(providers, config_reader=config_reader)
