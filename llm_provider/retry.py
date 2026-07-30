"""Экспоненциальный backoff с джиттером для вызовов LLM."""

from __future__ import annotations

import logging
import random
import time
from typing import Callable

from .base import LLMRequest, LLMTransientError

log = logging.getLogger("llm_provider.retry")

MAX_ATTEMPTS = 6
BASE_DELAY = 1.0      # сек
MAX_DELAY = 30.0


def call_with_retry(
    fn: Callable[[LLMRequest], tuple[str, int, int]],
    req: LLMRequest,
    max_attempts: int = MAX_ATTEMPTS,
) -> tuple[str, int, int, int]:
    """Возвращает (text, prompt_tokens, completion_tokens, attempts).

    LLMPermanentError наружу пробрасывается сразу — ретраить нечего.
    """
    last: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            text, pt, ct = fn(req)
            return text, pt, ct, attempt
        except LLMTransientError as exc:
            last = exc
            if attempt == max_attempts:
                break
            delay = min(BASE_DELAY * 2 ** (attempt - 1), MAX_DELAY)
            delay *= 0.5 + random.random()  # джиттер: 0.5x–1.5x
            log.warning(
                "LLM transient error (попытка %s/%s), retry через %.1fs: %s",
                attempt, max_attempts, delay, exc,
            )
            time.sleep(delay)

    raise LLMTransientError(f"Исчерпаны {max_attempts} попытки: {last}") from last
