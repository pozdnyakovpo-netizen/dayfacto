"""Генератор постов ВЭД-канала.

Отличие от services/editorial/generator.py: на вход подаётся не сырой
текст, а уже проверенная структура из ranking.scorers.ved_extract.
Модель пишет связный текст, но цифры, коды и даты берутся только из
полей, прошедших валидатор.
"""

from __future__ import annotations

import datetime
import logging
import re
from dataclasses import dataclass, field

from llm_provider import LLMError, LLMParseError, LLMRequest

log = logging.getLogger("editorial.ved")

SCHEMA = {
    "type": "object",
    "required": ["headline", "what_changes", "who", "what_to_do"],
    "properties": {
        "headline": {"type": "string"},
        "what_changes": {"type": "string"},
        "who": {"type": "string"},
        "what_to_do": {"type": "string"},
    },
}

BRAND = """Ты - редактор Telegram-канала для участников ВЭД.

Читатели - декларанты, логисты, импортёры и экспортёры. Они читают
нормативку каждый день и мгновенно чувствуют подделку под экспертизу.

ТОН
Сухой, конкретный, с цифрами. Как у отраслевого юриста, не как у блогера.
Уважение к времени читателя - это и есть тон.

ЗАПРЕЩЕНО
- кликбейт: "шок", "вы не поверите", "срочно", "важно"
- восклицательные знаки, КАПС, эмодзи в тексте
- канцелярит: "как сообщается", "в целях реализации"
- штампы ИИ: "важно отметить", "в мире, где", "не секрет, что"
- призывы вместо последствий: "будьте внимательны", "следите за новостями"
- ЛЮБЫЕ цифры, коды, даты и номера документов, которых нет в данных ниже
- названия органов и документов, которых нет в поле Документ
  (нет документа в данных - пиши «введено требование», без ссылки)

ЧТО ПИСАТЬ В КАЖДОМ БЛОКЕ

headline - что меняется и с какого числа. До 80 символов, законченная
мысль. Дату ставь только если она есть в данных. Без интриги.

what_changes - два-три предложения фактуры. Что именно изменилось,
каким документом. Только факт, без интерпретации.

who - кого это касается. Называй конкретные коды ТН ВЭД, страны и
направление из данных. Читатель должен найти глазами своё.
Если кодов нет - опиши товарную группу словами из данных.

what_to_do - конкретное действие и срок. Пересчитать себестоимость,
подать декларацию до даты, обновить шаблон, проверить код с декларантом.
Одно-два предложения. Не призыв, а действие с последствием.

Если срок в данных помечен как relative или conditional - напиши, что
дата вступления пока не определена. НЕ вычисляй её сам.

Ответь одним объектом JSON и ничем больше. Ключи: headline,
what_changes, who, what_to_do. Без пояснений, без markdown."""


@dataclass
class VedDraft:
    story_id: int = 0
    headline: str = ""
    what_changes: str = ""
    who: str = ""
    what_to_do: str = ""
    source_line: str = ""
    provider: str = ""
    tokens: int = 0
    problems: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems and bool(self.headline)

    def render(self) -> str:
        parts = [self.headline, ""]
        if self.what_changes:
            parts += [self.what_changes, ""]
        if self.who:
            parts += ["Кого касается: " + self.who, ""]
        if self.what_to_do:
            parts += ["Что делать: " + self.what_to_do, ""]
        if self.source_line:
            parts.append(self.source_line)
        return "\n".join(parts).strip()


def _facts_block(c: dict) -> str:
    """Данные, из которых модели разрешено брать факты."""
    rows = [
        ("Что изменилось", c.get("what")),
        ("Тип изменения", c.get("change_type")),
        ("Коды ТН ВЭД", ", ".join(c.get("tnved_codes") or [])),
        ("Страны", ", ".join(c.get("countries") or [])),
        ("Направление", c.get("direction")),
        ("Товары", c.get("goods")),
        ("Прежнее значение", c.get("value_old")),
        ("Новое значение", c.get("value_new")),
        ("Дата вступления", c.get("effective_date")),
        ("Статус даты", c.get("date_status")),
        ("Последствие", c.get("impact")),
        ("Суть последствия", c.get("impact_note")),
        ("Документ", c.get("doc_number")),
    ]
    return "\n".join("%s: %s" % (k, v) for k, v in rows if v)


def _forbidden_numbers(post: str, allowed: str) -> list:
    """Цифры и коды в посте, которых нет в разрешённых данных."""
    bad = []
    allowed_digits = re.sub(r"[^\d]", "", allowed)
    for token in re.findall(r"\d[\d\s.,%]*\d|\d", post):
        digits = re.sub(r"\D", "", token)
        if not digits:
            continue
        if digits in allowed_digits:
            continue
        loose = r"\s*".join(digits)
        if re.search(loose, allowed):
            continue
        bad.append(token.strip())
    return bad


CLICHE = [
    "будьте внимательны", "следите за", "важно отметить", "не секрет",
    "в мире, где", "как сообщается", "рекомендуем ознакомиться",
    "обратите внимание", "не пропустите",
]


def _check(d: VedDraft, facts: str) -> None:
    if not d.headline:
        d.problems.append("нет заголовка")
        return
    if len(d.headline) > 100:
        d.problems.append("заголовок длиннее 100 символов")
    if "!" in d.headline or d.headline.isupper():
        d.problems.append("восклицание или капс в заголовке")

    whole = " ".join([d.headline, d.what_changes, d.who, d.what_to_do]).lower()
    for c in CLICHE:
        if c in whole:
            d.problems.append("штамп: %s" % c)

    bad = _forbidden_numbers(
        " ".join([d.headline, d.what_changes, d.who, d.what_to_do]), facts
    )
    if bad:
        d.problems.append("цифры вне данных: %s" % ", ".join(bad[:5]))

    if not d.what_to_do:
        d.problems.append("нет блока «что делать»")


def generate(router, change: dict, story_id: int = 0,
             source_url: str = "", source_name: str = "alta.ru") -> VedDraft:
    """change - словарь из ranking.scorers.ved_extract.extract()."""
    d = VedDraft(story_id=story_id)

    if not change.get("publishable"):
        d.problems.append("сюжет не прошёл отбор: %s" % change.get("reason", ""))
        return d

    facts = _facts_block(change)
    if len(facts) < 40:
        d.problems.append("слишком мало данных для поста")
        return d

    today = datetime.date.today().isoformat()
    user = (
        "Сегодня " + today + ". Если дата вступления уже прошла, "
        "пиши что требование действует, а не что оно вступит. "
        "Не начинай блоки словами из их заголовков.\n\n"
        "Напиши пост по данным ниже. Используй ТОЛЬКО эти факты.\n\n"
        "ДАННЫЕ:\n" + facts
    )

    req = LLMRequest(
        system=BRAND, user=user, json_schema=SCHEMA,
        temperature=0.3, max_tokens=800,
        meta={"task": "ved_editorial", "story_id": story_id},
    )

    primary = router._resolve("ved_editorial").name
    order = [primary] + [n for n in router.providers if n != primary]
    last = "провайдеры недоступны"

    for name in order:
        try:
            resp = router.providers[name].generate(req)
        except LLMParseError as exc:
            last = "%s: пустой или невалидный ответ" % name
            log.warning("%s: %r", name, (exc.raw or "")[:120])
            continue
        except LLMError as exc:
            last = "%s недоступен" % name
            log.warning("%s недоступен: %s", name, exc)
            continue

        data = resp.data or {}
        d.headline = str(data.get("headline", "")).strip()
        d.what_changes = str(data.get("what_changes", "")).strip()
        d.who = str(data.get("who", "")).strip()
        d.what_to_do = str(data.get("what_to_do", "")).strip()
        d.provider = name
        d.tokens = getattr(resp, "total_tokens", 0)

        doc = change.get("doc_number") or ""
        url = source_url or ""
        d.source_line = "Источник: %s%s" % (
            doc + " — " if doc else "", url or source_name
        )

        _check(d, facts)
        return d

    d.problems.append(last)
    return d
