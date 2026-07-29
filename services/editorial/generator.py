"""Генерация текста поста.

Три вещи, ради которых этот модуль существует отдельно от промпта:

1. Перебор провайдеров. GigaChat отказывается писать про политику и войну,
   а это заметная доля ленты. Отказ распознаётся по отсутствию JSON, и
   тогда задача уходит следующему провайдеру.
2. Проверка результата. Модель может вернуть валидный JSON с пустой
   врезкой или кликбейтным заголовком. Такой пост не публикуется
   автоматически, а уходит человеку.
3. Чистка. Хештеги приходят то с решёткой, то без, то продублированные
   внутри текста.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from llm_provider import LLMError, LLMParseError, LLMRequest
from services.editorial.checks import check_dates

log = logging.getLogger("editorial.generator")

SCHEMA = {
    "type": "object",
    "required": ["headline", "body", "why_it_matters"],
    "properties": {
        "headline": {"type": "string"},
        "body": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "hashtags": {"type": "array"},
    },
}

BRAND = """Ты - редактор Telegram-канала @DayFacto.

Канал публикует только то, что реально меняет жизнь людей: законы,
тарифы, выплаты, происшествия, решения, вступающие в силу.

ТОН
Сдержанный, фактологичный. Как у информагентства, не как у блогера.
Никакой оценки событий, никаких эмоций, никакого нагнетания.

ЗАПРЕЩЕНО
- кликбейт: "шок", "вы не поверите", "невероятно", "срочно"
- восклицательные знаки и КАПС
- канцелярит: "как сообщается", "по имеющимся данным"
- штампы ИИ: "важно отметить", "в мире, где", "не секрет, что"
- любые факты, цифры и цитаты, которых нет в исходном тексте

ПРАВИЛА
Один пост - одно событие. Если в источнике несколько разных событий,
пиши только о главном, остальные игнорируй.
Заголовок - законченная мысль до 80 символов, без обрыва на середине.
Тело - 2-3 предложения. Только то, что произошло, и ключевые цифры.
Если факт предварительный - так и пиши ("по предварительным данным").
Всегда называй место события (город, регион). Если в источнике места
нет - не пиши "в одном из городов", а сообщи, что место не уточняется.

ВРЕЗКА why_it_matters
Одно предложение: как это коснётся ЖИТЕЛЯ РОССИИ. Конкретно.
Если событие за рубежом и на жизнь в России не влияет - пустая строка.
Не призывай к действию: врезка сообщает последствие, а не совет.
Хорошо: "Владельцы автомобилей старше 10 лет будут платить налог выше."
Плохо: "Это важное событие для отрасли." (ни о ком конкретно)
Плохо: "Будьте осторожны." (призыв, а не последствие)
Если реальных последствий для обычных людей нет - верни пустую строку.

Ответь одним объектом JSON, без markdown и пояснений:
{"headline": "...", "body": "...", "why_it_matters": "...", "hashtags": ["тема", "регион"]}"""

CLICKBAIT = re.compile(r"(шок|сенсац|вы не поверите|невероятн|срочно!|!!)", re.I)
AI_CLICHE = re.compile(r"(важно отметить|в мире, где|не секрет|стоит отметить)", re.I)

# Врезка должна называть ПОСЛЕДСТВИЕ, а не призывать к действию.
# «Жителям следует быть бдительными» — призыв: он ничего не сообщает,
# подставляется к любой новости и потому бесполезен.
APPEAL = re.compile(
    # Не список глаголов (дыры вылезают бесконечно), а конструкция:
    # долженствование, адресованное читателю. Последствие описывает,
    # что произойдёт; призыв — что читателю делать.
    r"(следует|стоит|нужно|необходимо|рекомендуется|важно|лучше)\s+\S+\s*(ся\b|ть\b|ться\b)|"
    r"(следует|стоит|нужно|необходимо|рекомендуется)\s+\w+ить|"
    r"(следует|стоит|нужно|необходимо)\s+(быть|обрати|учиты|помни|знать)|"
    r"^(будьте|соблюдайте|проявляйте|следите|берегите|проверьте|не сообщайте)|"
    r"(меры предосторожност|быть бдительн|быть осторожн|обратить внимание)", re.I)

# Признак неконкретности: событие без места и без исхода.
VAGUE = re.compile(
    r"(в одном из|в некоторых|в ряде (городов|регионов)|"
    r"неизвестн(ый|ая|ые) (мужчин|женщин|лиц)|где-то)", re.I)


@dataclass
class Draft:
    story_id: int
    headline: str = ""
    body: str = ""
    why_it_matters: str = ""
    hashtags: list = field(default_factory=list)
    provider: str = ""
    tokens: int = 0
    ok: bool = False
    problems: list = field(default_factory=list)

    def render(self) -> str:
        """Готовый текст для Telegram (HTML-разметка)."""
        parts = [f"<b>{self.headline}</b>", "", self.body]
        if self.why_it_matters:
            parts += ["", f"<blockquote>💡 {self.why_it_matters}</blockquote>"]
        if self.hashtags:
            parts += ["", " ".join(f"#{h}" for h in self.hashtags[:3])]
        return "\n".join(parts)


def _clean_tag(tag: str) -> str:
    """Хештег приходит то с решёткой, то без, то с пробелами."""
    t = re.sub(r"[^\w]", "", str(tag).lstrip("#"), flags=re.UNICODE)
    return t[:24]


def _validate(d: Draft, source: str = "") -> None:
    """Заполняет d.problems и d.ok. Пустой список проблем = можно публиковать."""
    p = d.problems
    if not d.headline or len(d.headline) < 15:
        p.append("заголовок пустой или слишком короткий")
    if len(d.headline) > 100:
        p.append("заголовок длиннее 100 символов")
    if not d.body or len(d.body) < 40:
        p.append("тело слишком короткое")
    if CLICKBAIT.search(d.headline + " " + d.body):
        p.append("признаки кликбейта")
    if AI_CLICHE.search(d.body):
        p.append("штампы ИИ в тексте")
    if not d.why_it_matters:
        # Не ошибка модели, а сигнал отбора: если последствий нет,
        # это, скорее всего, и не новость для нашего канала.
        p.append("нет последствий для читателя")
    elif APPEAL.search(d.why_it_matters):
        p.append("во врезке призыв вместо последствия")
    if VAGUE.search(d.headline + " " + d.body):
        p.append("событие без конкретики (места, исхода)")

    # Сверка с источником: модель не должна вводить факты, которых
    # в исходном материале нет. Самый частый случай - выдуманная дата.
    full = f"{d.headline} {d.body} {d.why_it_matters}"
    bad_dates = check_dates(full, source)
    if bad_dates:
        p.append("даты нет в источнике: " + ", ".join(bad_dates[:3]))

    d.ok = not p


def generate(router, story_id: int, title: str, body: str = "") -> Draft:
    d = Draft(story_id=story_id)

    # Без исходного текста модель пишет пост из одного заголовка и
    # додумывает детали: даты, число пострадавших, места. Проверить их
    # не с чем, поэтому такие сюжеты в редактуру не отдаём вовсе.
    if len((body or '').strip()) < 100:
        d.problems.append('нет исходного текста, только заголовок')
        return d
    req = LLMRequest(
        system=BRAND,
        user=f"{title}\n\n{(body or '')[:2000]}",
        json_schema=SCHEMA,
        temperature=0.3,
        max_tokens=800,
        meta={"task": "editorial", "story_id": story_id},
    )

    primary = router._resolve("editorial").name
    order = [primary] + [n for n in router.providers if n != primary]
    last = "провайдеры недоступны"

    for i, name in enumerate(order):
        try:
            resp = router.providers[name].generate(req)
        except LLMParseError as exc:
            if "{" not in (exc.raw or ""):
                log.info("%s отказался писать: %s", name, title[:50])
                last = f"{name} отказался"
            else:
                log.warning("%s вернул невалидный JSON", name)
                last = f"{name}: невалидный JSON"
            continue
        except LLMError as exc:
            log.warning("%s недоступен: %s", name, exc)
            last = f"{name} недоступен"
            continue

        data = resp.data or {}
        d.headline = str(data.get("headline", "")).strip()
        d.body = str(data.get("body", "")).strip()
        d.why_it_matters = str(data.get("why_it_matters") or "").strip()
        d.hashtags = [t for t in (_clean_tag(x) for x in data.get("hashtags", [])) if t]
        d.provider = name
        d.tokens = resp.total_tokens
        if i > 0:
            log.info("написано резервным провайдером %s", name)
        _validate(d, body or '')
        return d

    d.problems.append(last)
    return d
