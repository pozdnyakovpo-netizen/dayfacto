"""Проверки готового поста, требующие сверки с источником.

Обычная валидация смотрит только на текст. Эти проверки сравнивают
текст с исходным материалом — так ловятся факты, которых в источнике
не было. Самый частый случай: модель уверенно называет дату, которой
в новости нет.
"""

from __future__ import annotations

import re

MONTHS = ("январ", "феврал", "март", "апрел", "мая", "мае", "июн", "июл",
          "август", "сентябр", "октябр", "ноябр", "декабр")

DATE_PAT = re.compile(
    r"(\d{1,2}\s+(?:" + "|".join(MONTHS) + r")\w*)|"
    r"(\d{1,2}\.\d{1,2}\.\d{2,4})|"
    r"(с \d{1,2}\s+(?:" + "|".join(MONTHS) + r")\w*)", re.IGNORECASE)

NUM_PAT = re.compile(r"\b\d[\d\s.,]{2,}\b")


def _norm(s: str) -> str:
    return re.sub(r"[\s.,]", "", s or "").lower()


def check_dates(post_text: str, source_text: str) -> list[str]:
    """Даты в посте, которых нет в источнике.

    Если источника нет вовсе, любая дата в посте подозрительна: сверить
    её не с чем, а модель охотно подставляет правдоподобную. Именно так
    в пост попало «29 апреля» вместо июля — проверка при пустом источнике
    раньше молча пропускала всё.
    """
    if not source_text:
        return [m.group(0) for m in DATE_PAT.finditer(post_text or "")]
    src = _norm(source_text)
    bad = []
    for m in DATE_PAT.finditer(post_text or ""):
        frag = m.group(0)
        # Сверяем «число + месяц» без учёта падежа: в источнике может
        # быть «29 июля», а в посте «29 июля» с другим окончанием.
        num = re.match(r"\D*(\d{1,2})", frag)
        month = next((mo for mo in MONTHS if mo in frag.lower()), None)
        if num and month:
            if not (num.group(1) in source_text and month in src):
                bad.append(frag)
        elif _norm(frag) not in src:
            bad.append(frag)
    return bad


def check_numbers(post_text: str, source_text: str) -> list[str]:
    """Крупные числа, которых нет в источнике."""
    if not source_text:
        return [m.group(0) for m in DATE_PAT.finditer(post_text or "")]
    src = _norm(source_text)
    return [m.group(0).strip() for m in NUM_PAT.finditer(post_text or "")
            if _norm(m.group(0)) not in src]
