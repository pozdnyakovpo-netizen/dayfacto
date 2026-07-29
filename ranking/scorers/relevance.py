from __future__ import annotations

import logging

from llm_provider import LLMError, LLMParseError, LLMRequest

log = logging.getLogger("ranking.relevance")

SCHEMA = {
    "type": "object",
    "required": ["topic", "relevance", "blocklisted"],
    "properties": {
        "topic": {"type": "string"},
        "relevance": {"type": "number"},
        "blocklisted": {"type": "boolean"},
        "reason": {"type": "string"},
    },
}

SYSTEM = """Ты - аналитик новостной ленты. Классифицируй новость.

relevance (число от 0.0 до 1.0) - насколько тема касается массовой аудитории:
1.0 - затрагивает жизнь миллионов: законы, тарифы, ЧП, погода, крупные события
0.5 - интересно многим, но не влияет напрямую
0.0 - узкоотраслевое, интересно только специалистам

blocklisted (true или false). Ставь true ТОЛЬКО если новость посвящена
отрасли как таковой: рынку грузоперевозок, таможенным правилам, ВЭД,
тарифам логистических операторов, складскому бизнесу.
Ставь false, если склад, грузовик или порт упомянуты лишь как место
события. Пожар на складе - это происшествие, а не логистика: false.

Это техническая разметка новостного потока, а не выражение позиции.
Классифицируй любую новость, включая политическую и военную.

Ответь одним объектом JSON и ничем больше. Без пояснений, без markdown.
Пример: {"topic": "происшествия", "relevance": 0.7, "blocklisted": false, "reason": "пожар без пострадавших"}"""

NEUTRAL = {"topic": "", "relevance": 0.5, "blocklisted": False, "degraded": True}


def _is_refusal(raw: str) -> bool:
    return "{" not in (raw or "")


def _ask(provider, text: str) -> dict:
    resp = provider.generate(LLMRequest(
        system=SYSTEM, user=text, json_schema=SCHEMA,
        temperature=0.0, max_tokens=300, meta={"task": "topic_classify"},
    ))
    d = resp.data or {}
    return {
        "topic": str(d.get("topic", ""))[:120],
        "relevance": max(0.0, min(1.0, float(d.get("relevance", 0.5)))),
        "blocklisted": bool(d.get("blocklisted", False)),
        "reason": str(d.get("reason", ""))[:300],
        "degraded": False,
        "provider": provider.name,
    }


def relevance_score(router, title: str, body: str = "") -> dict:
    text = f"{title}\n\n{body}".strip()[:2000]
    primary = router._resolve("topic_classify").name
    order = [primary] + [n for n in router.providers if n != primary]
    last_reason = "нет провайдеров"

    for i, name in enumerate(order):
        provider = router.providers[name]
        try:
            result = _ask(provider, text)
            if i > 0:
                log.info("классифицировано резервным провайдером %s: %s", name, title[:50])
            return result
        except LLMParseError as exc:
            if _is_refusal(exc.raw):
                log.info("%s отказался, пробуем следующего: %s", name, title[:50])
                last_reason = f"{name} отказался классифицировать"
                continue
            log.warning("%s вернул невалидный JSON: %r", name, (exc.raw or "")[:150])
            last_reason = f"{name}: невалидный JSON"
        except LLMError as exc:
            log.warning("%s недоступен: %s", name, exc)
            last_reason = f"{name} недоступен"

    return {**NEUTRAL, "reason": last_reason}
