#!/usr/bin/env python3
"""Календарь дедлайнов ВЭД-канала.

То, чего нет у агрегаторов: система помнит все будущие даты вступления
в силу и сама напоминает читателю заранее.

Три типа выпуска:
  1. Напоминание за 30 дней  - есть время подготовиться.
  2. Напоминание за 7 дней   - пора действовать.
  3. Напоминание накануне    - последний день.
  4. Дайджест по понедельникам - что вступает в силу на этой неделе.

Данные берутся из кэша извлечений (ved_extractions), который заполняет
build_outbox.py. Отдельных обращений к модели нет - напоминания
собираются из уже проверенных фактов. Это важно: повторный проход
модели мог бы исказить цифры, а здесь они те же, что прошли валидатор.

Использование:
    docker compose run --rm -v /root/dayfacto/outbox:/app/outbox \\
        ingestion python tools/build_reminders.py
    docker compose run --rm -v /root/dayfacto/outbox:/app/outbox \\
        ingestion python tools/build_reminders.py --digest
"""

import argparse
import json
import os
import pathlib
import sys
from datetime import date, timedelta

sys.path.insert(0, "/app")

from sqlalchemy import text                      # noqa: E402

from db.session import get_session               # noqa: E402

OUT = pathlib.Path(os.environ.get("OUTBOX_PATH", "/app/outbox/pending.json"))

DDL_SENT = text("""
CREATE TABLE IF NOT EXISTS ved_reminders_sent (
    raw_item_id UUID NOT NULL,
    kind        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (raw_item_id, kind)
)
""")

SQL_UPCOMING = text("""
SELECT e.raw_item_id,
       e.payload,
       r.url
  FROM ved_extractions e
  JOIN raw_items r ON r.id = e.raw_item_id
 WHERE e.payload->>'date_status' = 'exact'
   AND e.payload->>'effective_date' <> ''
   AND (e.payload->>'publishable')::boolean IS TRUE
""")

MONTHS = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}


def ru_date(d: date) -> str:
    return "%d %s" % (d.day, MONTHS[d.month])


def audience(c: dict) -> str:
    """Кого касается - из проверенных полей, без обращения к модели."""
    parts = []
    codes = c.get("tnved_codes") or []
    if codes:
        parts.append("коды " + ", ".join(codes[:6]))
    countries = c.get("countries") or []
    if countries:
        parts.append(", ".join(countries[:6]))
    goods = (c.get("goods") or "").strip()
    if goods and not codes:
        parts.append(goods[:110].rsplit(" ", 1)[0] + "…" if len(goods) > 110 else goods)
    return "; ".join(parts)


def reminder_text(c: dict, eff: date, days: int, url: str) -> str:
    what = (c.get("what") or "").strip().rstrip(".")
    doc = (c.get("doc_number") or "").strip()

    if days == 0:
        head = "Сегодня вступает в силу: %s" % what
        lead = "Последний день по старым правилам."
    elif days == 1:
        head = "Завтра вступает в силу: %s" % what
        lead = "Остался один день."
    elif days <= 7:
        head = "Через %d дн. вступает в силу: %s" % (days, what)
        lead = "До вступления в силу %d дн." % days
    else:
        head = "Через месяц: %s" % what
        lead = "До вступления в силу %d дней - есть время подготовиться." % days

    lines = [head, "", "%s Дата вступления - %s." % (lead, ru_date(eff))]

    aud = audience(c)
    if aud:
        lines += ["", "Кого касается: " + aud]

    old, new = c.get("value_old") or "", c.get("value_new") or ""
    if new:
        if old:
            lines += ["", "Значение: было %s, станет %s." % (old, new)]
        else:
            lines += ["", "Новое значение: %s." % new]

    note = (c.get("impact_note") or "").strip()
    if note:
        note = note[0].upper() + note[1:]
        lines += ["", note.rstrip(".") + "."]

    src = "Источник: "
    src += (doc + " — ") if doc else ""
    src += url or "alta.ru"
    lines += ["", src]
    return "\n".join(lines)


def digest_text(rows, monday: date, sunday: date) -> str:
    lines = ["Что вступает в силу на этой неделе",
             "",
             "С %s по %s." % (ru_date(monday), ru_date(sunday)),
             ""]
    for eff, c, _url in rows:
        what = (c.get("headline") or c.get("what") or "").strip().rstrip(".")
        aud = audience(c)
        if len(what) > 80:
            cut = what[:80].rsplit(" ", 1)[0]
            what = cut + "…"
        line = "%s — %s" % (ru_date(eff), what)
        if aud:
            short = aud if len(aud) <= 50 else aud[:50].rsplit(" ", 1)[0] + "…"
            line += " (%s)" % short
        lines.append(line)
    lines += ["", "Подробности по каждому пункту были в постах выше."]
    return "\n".join(lines)


def load_queue():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not OUT.exists():
        return []
    try:
        return json.loads(OUT.read_text() or "[]")
    except json.JSONDecodeError:
        return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--digest", action="store_true",
                    help="еженедельный дайджест вместо напоминаний")
    ap.add_argument("--today", default="",
                    help="переопределить дату, формат ГГГГ-ММ-ДД (для теста)")
    ap.add_argument("--dry", action="store_true",
                    help="показать, но не писать в очередь")
    a = ap.parse_args()

    today = date.fromisoformat(a.today) if a.today else date.today()

    session = get_session()
    session.execute(DDL_SENT)
    session.commit()

    items = []
    for raw_id, payload, url in session.execute(SQL_UPCOMING):
        c = json.loads(payload) if isinstance(payload, str) else payload
        try:
            eff = date.fromisoformat(c.get("effective_date"))
        except (TypeError, ValueError):
            continue
        items.append((raw_id, eff, c, url or ""))

    if not items:
        print("нет сюжетов с точной датой вступления")
        session.close()
        return 0

    queue = load_queue()

    # --- дайджест недели ---------------------------------------------
    if a.digest:
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        week = sorted([(e, c, u) for _i, e, c, u in items
                       if monday <= e <= sunday])
        if not week:
            print("на этой неделе ничего не вступает в силу")
            session.close()
            return 0
        text_ = digest_text(week, monday, sunday)
        print("=" * 55)
        print(text_)
        if not a.dry:
            queue.append({
                "item_id": "digest-%s" % monday.isoformat(),
                "title": "Дайджест недели %s" % monday.isoformat(),
                "text": text_,
                "doc_number": "",
                "effective_date": "",
            })
            OUT.write_text(json.dumps(queue, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            print("\nдобавлено в очередь: 1 дайджест")
        session.close()
        return 0

    # --- напоминания --------------------------------------------------
    sent = {(str(r[0]), r[1]) for r in
            session.execute(text("SELECT raw_item_id, kind "
                                 "FROM ved_reminders_sent"))}

    added = 0
    for raw_id, eff, c, url in sorted(items, key=lambda x: x[1]):
        days = (eff - today).days
        if days < 0:
            continue
        if days <= 2:
            kind = "d1"
        elif 3 <= days <= 8:
            kind = "d7"
        elif 28 <= days <= 32:
            kind = "d30"
        else:
            continue

        if (str(raw_id), kind) in sent:
            continue

        text_ = reminder_text(c, eff, days, url)
        print("=" * 55)
        print("[%s, через %d дн.]" % (kind, days))
        print(text_)

        if not a.dry:
            queue.append({
                "item_id": "%s-%s" % (raw_id, kind),
                "title": "Напоминание %s: %s" % (kind, (c.get("what") or "")[:60]),
                "text": text_,
                "doc_number": c.get("doc_number", ""),
                "effective_date": c.get("effective_date", ""),
            })
            session.execute(
                text("INSERT INTO ved_reminders_sent (raw_item_id, kind) "
                     "VALUES (:i, :k) ON CONFLICT DO NOTHING"),
                {"i": raw_id, "k": kind},
            )
            added += 1

    if not a.dry and added:
        session.commit()
        OUT.write_text(json.dumps(queue, ensure_ascii=False, indent=2),
                       encoding="utf-8")

    session.close()
    print("\nнапоминаний добавлено: %d" % added)
    if not added:
        print("(на сегодня напоминать не о чем)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
