"""Устойчивый разбор JSON из ответа LLM.

Модели любят: обернуть в ```json, добавить преамбулу, поставить запятую перед
закрывающей скобкой. Всё это чиним здесь, а не в каждом сервисе.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from .base import LLMParseError

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _first_balanced_object(s: str) -> str | None:
    """Найти первый сбалансированный {...}, игнорируя скобки внутри строк."""
    start = s.find("{")
    if start == -1:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return None


def extract_json(text: str) -> dict[str, Any]:
    candidates: list[str] = []

    fenced = _FENCE.search(text or "")
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(text or "")

    for cand in candidates:
        cand = cand.strip()
        for attempt in (cand, _first_balanced_object(cand)):
            if not attempt:
                continue
            for cleaned in (attempt, _TRAILING_COMMA.sub(r"\1", attempt)):
                try:
                    parsed = json.loads(cleaned)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
                raise LLMParseError("Ожидался JSON-объект, получен другой тип", raw=text)

    raise LLMParseError("Не удалось извлечь валидный JSON из ответа", raw=text or "")


def validate_schema(data: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    """Минимальная валидация: required-поля и типы верхнего уровня.

    Намеренно без jsonschema — нам нужен быстрый гейт «поля на месте», а не
    полная спецификация. Если схемы усложнятся — заменить на jsonschema здесь,
    интерфейс не меняется.
    """
    types = {
        "string": str, "number": (int, float), "integer": int,
        "boolean": bool, "array": list, "object": dict,
    }

    for key in schema.get("required", []):
        if key not in data:
            raise LLMParseError(f"В ответе отсутствует обязательное поле: {key}")

    for key, spec in (schema.get("properties") or {}).items():
        if key not in data or data[key] is None:
            continue
        expected = spec.get("type")
        if isinstance(expected, str) and expected in types:
            if not isinstance(data[key], types[expected]):
                raise LLMParseError(
                    f"Поле {key}: ожидался {expected}, получен {type(data[key]).__name__}"
                )
