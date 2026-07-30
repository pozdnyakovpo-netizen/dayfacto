"""Критерий готовности модуля: реальный вызов возвращает валидный JSON.

Запуск внутри контейнера:
    docker compose run --rm editorial python -m llm_provider.smoke_test
"""

from __future__ import annotations

import json
import logging
import sys

from .base import LLMRequest
from .router import build_default_router

SCHEMA = {
    "type": "object",
    "required": ["headline", "body", "hashtags"],
    "properties": {
        "headline": {"type": "string"},
        "body": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "hashtags": {"type": "array"},
    },
}

SYSTEM = (
    "Ты — редактор премиального новостного Telegram-канала @DayFacto.\n"
    "Тон: сдержанный, фактологичный, без эмоциональной окраски.\n"
    "Никогда не используй кликбейт-слова, AI-штампы, канцеляризмы.\n"
    "Один пост = одно событие. Заголовок — законченная мысль.\n"
    "Используй ТОЛЬКО факты из предоставленного текста, ничего не домысливай.\n\n"
    'Ответь СТРОГО в JSON: {"headline": "...", "body": "...", '
    '"why_it_matters": "... или null", "hashtags": ["..."]}'
)

SAMPLE = (
    "Во Владимире произошел пожар на складе со стройматериалами. "
    "Площадь возгорания составила 600 квадратных метров. "
    "По предварительным данным, пострадавших нет, причина устанавливается."
)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    router = build_default_router()

    print("health:", router.health())

    resp = router.generate(
        "editorial",
        LLMRequest(
            system=SYSTEM,
            user=SAMPLE,
            json_schema=SCHEMA,
            temperature=0.3,
            meta={"task": "smoke", "story_id": 0},
        ),
    )

    print(f"\nprovider={resp.provider} model={resp.model} "
          f"tokens={resp.total_tokens} latency={resp.latency_ms}ms attempts={resp.attempts}\n")
    print(json.dumps(resp.data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
