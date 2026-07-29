from __future__ import annotations

import logging
import re
from datetime import date

from llm_provider import LLMError, LLMParseError, LLMRequest

log = logging.getLogger("ranking.ved")

SCHEMA = {
    "type": "object",
    "required": ["change_type", "what", "impact"],
    "properties": {
        "change_type": {"type": "string"},
        "what": {"type": "string"},
        "tnved_codes": {"type": "array", "items": {"type": "string"}},
        "countries": {"type": "array", "items": {"type": "string"}},
        "direction": {"type": "string"},
        "goods": {"type": "string"},
        "value_old": {"type": "string"},
        "value_new": {"type": "string"},
        "effective_date": {"type": "string"},
        "date_status": {"type": "string"},
        "date_raw": {"type": "string"},
        "impact": {"type": "string"},
        "impact_note": {"type": "string"},
        "doc_number": {"type": "string"},
        "stage": {"type": "string"},
    },
}

SYSTEM = """Ты - аналитик по внешнеэкономической деятельности.
Извлеки факты из материала. Ты НЕ оцениваешь важность и НЕ пишешь текст.

ЖЕЛЕЗНЫЕ ПРАВИЛА:
1. Бери только то, что прямо написано. Ничего не достраивай.
2. Нет сведений - оставь поле пустым. Пустое лучше выдуманного.
3. НИКОГДА не вычисляй дату сам. Если срок задан как период от
   опубликования - статус даты relative, саму дату не заполняй.
   Если вступление зависит от другого документа - статус conditional,
   дату не заполняй. Только прямо названную в тексте дату можно
   поставить со статусом exact в формате ГГГГ-ММ-ДД.
4. В поле date_raw дословно скопируй фрагмент про срок вступления.
5. Коды ТН ВЭД копируй посимвольно, с пробелами как в источнике.
6. Если указано прежнее значение - обязательно заполни value_old.

Возможные значения change_type: duty_rate, tnved_code, preference,
procedure, restriction, control, currency_control, court_practice,
rate_info. Если ничего не подходит - оставь пустым.

Возможные значения direction: import, export, transit, any.
Возможные значения stage: draft, adopted, published, in_force.

Значение impact выбирай так:
money - меняется сумма платежей: пошлина, льгота, преференция, акциз.
deadline - появляется срок, к которому надо что-то сделать.
risk - угроза отказа в выпуске, штрафа, простоя, запрета.
none - разговоры, намерения, статистика, служебные справочники,
мероприятия, задержания, товары для личного пользования.

Это техническая разметка, а не выражение позиции."""

EMPTY = {
    "change_type": "", "what": "", "tnved_codes": [], "countries": [],
    "direction": "", "goods": "", "value_old": "", "value_new": "",
    "effective_date": "", "date_status": "none", "date_raw": "",
    "impact": "none", "impact_note": "", "doc_number": "", "stage": "adopted",
    "degraded": True, "provider": "",
}

MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}


def _is_refusal(raw: str) -> bool:
    return "{" not in (raw or "")


def _norm(s: str) -> str:
    return re.sub(r"[\s\u00a0]+", " ", s or "").strip()


def _dates_in(text: str) -> set:
    found = set()
    for d, m, y in re.findall(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b", text):
        yy = int(y)
        yy += 2000 if yy < 100 else 0
        try:
            found.add(date(yy, int(m), int(d)))
        except ValueError:
            pass
    pat = r"\b(\d{1,2})\s+([а-яё]+)\s+(\d{4})"
    for d, mon, y in re.findall(pat, text.lower()):
        if mon in MONTHS:
            try:
                found.add(date(int(y), MONTHS[mon], int(d)))
            except ValueError:
                pass
    return found


def validate(c: dict, source_text: str) -> list:
    """Сверка с источником. Непустой список = публиковать нельзя."""
    problems = []
    src = _norm(source_text)
    digits_only = re.sub(r"[^\d\s]", " ", src)

    for code in c.get("tnved_codes") or []:
        digits = re.sub(r"\D", "", code)
        if not digits:
            problems.append("пустой код ТН ВЭД")
            continue
        if not re.search(r"\s*".join(digits), digits_only):
            problems.append("код %s отсутствует в источнике" % code)

    for key in ("value_old", "value_new"):
        val = c.get(key) or ""
        for n in re.findall(r"\d+(?:[.,]\d+)?", str(val)):
            variants = {n, n.replace(".", ","), n.replace(",", ".")}
            if not any(v in src for v in variants):
                problems.append("%s: число %s нет в источнике" % (key, n))

    status = c.get("date_status") or "none"
    eff = c.get("effective_date") or ""
    if status == "exact":
        if not eff:
            problems.append("date_status=exact, но дата пуста")
        else:
            try:
                d = date.fromisoformat(eff)
            except ValueError:
                problems.append("неразбираемая дата: %s" % eff)
            else:
                if d not in _dates_in(src):
                    problems.append("дата %s вычислена, её нет в источнике" % eff)
    elif status in ("relative", "conditional") and eff:
        problems.append("date_status=%s, но проставлена дата %s" % (status, eff))

    raw = _norm(c.get("date_raw") or "").lower()
    if len(raw) > 12 and raw not in src.lower():
        problems.append("date_raw не найден дословно")

    doc = c.get("doc_number") or ""
    m = re.search(r"№\s*([\w\d\-/]+)", doc)
    if m:
        num = m.group(1)
        if ("№ %s" % num) not in src and ("№%s" % num) not in src:
            problems.append("номер № %s отсутствует в источнике" % num)

    return problems


def is_publishable(c: dict) -> tuple:
    """Решение принимают правила, а не модель."""
    if not c.get("change_type"):
        return False, "не определён тип изменения"
    if (c.get("impact") or "none") == "none":
        return False, "нет последствия для участника ВЭД"
    has_target = any([
        c.get("tnved_codes"), c.get("countries"),
        c.get("direction"), c.get("goods"),
    ])
    if not has_target:
        return False, "не определён адресат"
    if c.get("stage") == "draft":
        return False, "стадия проекта, ещё не принято"
    if c.get("date_status") == "none" and c.get("change_type") != "court_practice":
        return False, "нет срока"
    old = c.get("value_old") or ""
    new = c.get("value_new") or ""
    if old and old == new:
        return False, "значение не изменилось"
    return True, "ok"


def _ask(provider, text: str) -> dict:
    resp = provider.generate(LLMRequest(
        system=SYSTEM, user=text, json_schema=SCHEMA,
        temperature=0.0, max_tokens=700, meta={"task": "ved_extract"},
    ))
    d = resp.data or {}
    out = dict(EMPTY)
    for k in EMPTY:
        if k in ("degraded", "provider"):
            continue
        v = d.get(k, out[k])
        if isinstance(out[k], list):
            out[k] = [str(x)[:40] for x in (v or [])][:20]
        else:
            out[k] = str(v or "")[:400]
    out["degraded"] = False
    out["provider"] = provider.name
    return out


def extract(router, title: str, body: str = "") -> dict:
    """Извлекает структуру, проверяет правилами и валидатором.

    Возвращает словарь полей плюс:
      publishable - можно ли публиковать автоматически
      reason      - почему нет
      problems    - список расхождений с источником
    """
    source = "%s\n\n%s" % (title, body)
    task = "Извлеки факты из материала ниже в JSON по схеме. "
    task += "Ответь одним объектом JSON и ничем больше. "
    task += "Используй РОВНО эти ключи верхнего уровня, без вложенности: "
    task += "change_type, what, tnved_codes, countries, direction, goods, "
    task += "value_old, value_new, effective_date, date_status, date_raw, "
    task += "impact, impact_note, doc_number, stage. "
    task += "В doc_number укажи ПОЛНОЕ название документа как в тексте: "
    task += "вид, орган, дата и номер. Не сокращай до одного номера. "
    task += "Если органа в тексте нет - оставь пустым, не додумывай. "
    task += "Пустой doc_number НЕ мешает заполнить остальные поля: "
    task += "change_type и impact определяй по сути изменения. "
    task += "Поля tnved_codes и countries - списки строк, остальные строки. "
    task += "Не создавай других ключей и не оборачивай ответ в список.\n\n"
    task += "МАТЕРИАЛ:\n"
    text = task + source.strip()[:3500]
    primary = router._resolve("ved_extract").name
    order = [primary] + [n for n in router.providers if n != primary]
    last_reason = "нет провайдеров"

    for i, name in enumerate(order):
        provider = router.providers[name]
        try:
            c = _ask(provider, text)
        except LLMParseError as exc:
            if _is_refusal(exc.raw):
                log.info("%s отказался: %s", name, title[:50])
                last_reason = "%s отказался" % name
                continue
            log.warning("%s невалидный JSON: %r", name, (exc.raw or "")[:150])
            last_reason = "%s: невалидный JSON" % name
            continue
        except LLMError as exc:
            log.warning("%s недоступен: %s", name, exc)
            last_reason = "%s недоступен" % name
            continue

        if i > 0:
            log.info("извлечено резервным %s: %s", name, title[:50])

        c = sanitize(c)
        ok, reason = is_publishable(c)
        problems = validate(c, source) if ok else []
        if problems:
            ok = False
            reason = "валидатор: " + "; ".join(problems)
        c["publishable"] = ok
        c["reason"] = reason
        c["problems"] = problems
        return c

    out = dict(EMPTY)
    out["publishable"] = False
    out["reason"] = last_reason
    out["problems"] = []
    return out


ALLOWED_IMPACT = {"money", "deadline", "risk", "none"}
ALLOWED_TYPE = {"duty_rate", "tnved_code", "preference", "procedure",
                "restriction", "control", "currency_control",
                "court_practice", "rate_info"}
ALLOWED_DATE = {"exact", "relative", "conditional", "none"}


def sanitize(c):
    if c.get("impact") not in ALLOWED_IMPACT:
        c["impact"] = "none"
    if c.get("change_type") not in ALLOWED_TYPE:
        c["change_type"] = ""
    if c.get("date_status") not in ALLOWED_DATE:
        c["date_status"] = "none"
    if c.get("date_status") == "none":
        c["effective_date"] = ""
    return c
