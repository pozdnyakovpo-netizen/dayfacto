#!/usr/bin/env python3
"""Сборщик ленты «Альта — Новое в программах» (ставки пошлин).

Лента нестандартная: заголовок — только дата, а в описании слеплено
несколько независимых изменений подряд. Обычный RSS-парсер положил бы
это одной записью, и модель разобрала бы кашу.

Здесь описание разбивается на отдельные пункты, и каждый ложится в
raw_items как самостоятельный материал.

Запуск (отдельно от основного ingestion):
    docker compose run --rm ingestion python tools/ingest_programs.py
"""

import hashlib
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app")

import feedparser                                # noqa: E402
from sqlalchemy.exc import IntegrityError        # noqa: E402

from db.models import RawItemModel, SourceModel  # noqa: E402
from db.session import get_session               # noqa: E402

FEED = "https://www.alta.ru/rss/programsnews/"
SOURCE_NAME = "Альта — Новое в программах"

# Дата-префикс нового пункта: не после предлогов и перед заглавной буквой.
DATE_RE = re.compile(
    r"(?<!\bс )(?<!\bдо )(?<!\bот )(?<!\bпо )(?<!\d)(\d{2}\.\d{2}\.\d{2})"
    r"(?!\d)\s+(?=[А-ЯЁ])"
)
# Склейка без пробела: "...с 01.08.26Обновлены ставки..."
GLUE_RE = re.compile(
    r"(?<=[а-яё0-9\)\.])(?=(?:Обновлен|Установлен|Ставк|Изменен|Введен|"
    r"Уточнен|Отменен|Продлен))"
)


def split_compound(text: str) -> list:
    """Разбивает слипшееся описание на отдельные изменения."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    marks = [m.start() for m in DATE_RE.finditer(text)]
    if len(marks) >= 2:
        parts, last = [], 0
        for pos in marks:
            if pos > last:
                chunk = text[last:pos].strip()
                if chunk:
                    parts.append(chunk)
                last = pos
        tail = text[last:].strip()
        if tail:
            parts.append(tail)
    else:
        parts = [text]

    out = []
    for p in parts:
        out.extend(x.strip() for x in GLUE_RE.split(p) if x.strip())
    return [o for o in out if len(o) > 25]


def _hash(source_id, piece: str) -> str:
    return hashlib.sha256(("%s:%s" % (source_id, piece)).encode()).hexdigest()


def main() -> int:
    session = get_session()
    source = (session.query(SourceModel)
              .filter(SourceModel.name == SOURCE_NAME).first())
    if not source:
        print("источник «%s» не найден в таблице sources" % SOURCE_NAME)
        session.close()
        return 1

    parsed = feedparser.parse(FEED)
    entries = parsed.entries
    if not entries:
        print("лента пуста или недоступна")
        session.close()
        return 1

    inserted = 0
    for entry in entries[:30]:
        day = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", None)
        raw = getattr(entry, "summary", "") or getattr(entry, "description", "")
        full = getattr(entry, "text", "") or ""
        if len(full) > len(raw):
            raw = full

        published_at = None
        if getattr(entry, "published_parsed", None):
            published_at = datetime(*entry.published_parsed[:6],
                                    tzinfo=timezone.utc)

        pieces = split_compound(raw)
        for piece in pieces:
            item = RawItemModel(
                source_id=source.id,
                source_type="rss",
                url=link,
                title=piece[:200],
                body=("Дата публикации: %s. %s" % (day, piece))[:8000],
                published_at=published_at,
                fetched_at=datetime.now(timezone.utc),
                raw_hash=_hash(source.id, piece),
                status="new",
            )
            session.add(item)
            try:
                session.commit()
                inserted += 1
                print("+ %s" % piece[:80])
            except IntegrityError:
                session.rollback()

    session.close()
    print("\nвставлено новых пунктов: %d" % inserted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
