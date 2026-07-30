"""Рубрика ТРОИС: таможенный реестр объектов интеллектуальной собственности."""
import html
import re

GROUPS = (
    ("added", r"Добавлены:\s*(.+?)(?=(?:Продлены|Исключены|Истек срок|Подробная|$))"),
    ("renewed", r"Продлены:\s*(.+?)(?=(?:Добавлены|Исключены|Истек срок|Подробная|$))"),
    ("removed", r"Исключены:\s*(.+?)(?=(?:Добавлены|Продлены|Истек срок|Подробная|$))"),
    ("expired", r"Истек срок:\s*(.+?)(?=(?:Добавлены|Продлены|Исключены|Подробная|$))"),
)
PERIOD = re.compile(r"с\s*(\d{2})\.(\d{2})\s*по\s*(\d{2})\.(\d{2})\.(\d{4})")
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря")


EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\u2190-\u2BFF\uFE0F\u3030\u303D\u3297\u3299]")


def _brands(chunk):
    out = []
    for b in chunk.split(","):
        b = EMOJI.sub("", b)
        b = re.sub(r"\s+", " ", b).strip(" .;·")
        if 1 < len(b) <= 60:
            out.append(b)
    return out


def parse(body):
    """Возвращает словарь групп и период или None."""
    if "Добавлены:" not in body and "Исключены:" not in body:
        return None
    data = {}
    for key, pat in GROUPS:
        m = re.search(pat, body, re.S)
        data[key] = _brands(m.group(1)) if m else []
    m = PERIOD.search(body)
    if m:
        d1, m1, d2, m2, y = m.groups()
        if m1 == m2:
            data["period"] = "%d\u2013%d %s %s" % (
                int(d1), int(d2), MONTHS[int(m2) - 1], y)
        else:
            data["period"] = "%d %s \u2014 %d %s %s" % (
                int(d1), MONTHS[int(m1) - 1], int(d2), MONTHS[int(m2) - 1], y)
    else:
        data["period"] = ""
    return data


def _chips(items, limit=14):
    esc = [html.escape(x, quote=False) for x in items[:limit]]
    tail = "" if len(items) <= limit else " и ещё %d" % (len(items) - limit)
    return " · ".join("<code>%s</code>" % x for x in esc) + tail


def build(data, url="https://www.alta.ru/rois/"):
    add, rem, exp, ren = (data["added"], data["removed"],
                          data["expired"], data["renewed"])
    if not (add or rem or exp):
        return None, None

    head = "ТРОИС: реестр пополнился на %d знак%s" % (
        len(add), "" if len(add) % 10 == 1 and len(add) % 100 != 11
        else "а" if 2 <= len(add) % 10 <= 4 and not 12 <= len(add) % 100 <= 14
        else "ов") if add else "ТРОИС: изменения в реестре"

    out = ["<b>%s</b>" % html.escape(head, quote=False)]
    if data["period"]:
        out += ["", "▪ Период %s" % data["period"]]

    if add:
        out += ["", "<b>Новый риск при ввозе</b>", _chips(add),
                "Таможня вправе приостановить выпуск товаров с этими "
                "знаками. Нужно согласие правообладателя или подтверждение "
                "легальности ввоза."]

    freed = []
    if rem:
        freed.append("исключены: " + _chips(rem, 8))
    if exp:
        freed.append("истёк срок: " + _chips(exp, 10))
    if freed:
        out += ["", "<b>Защита снята</b>"] + freed

    if ren:
        out += ["", "<b>Продлены</b>", _chips(ren, 10)]

    out += ["", "Реестр ФТС · <a href=\"%s\">смотреть полностью</a>" % url]
    return head, "\n".join(out)
