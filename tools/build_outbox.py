#!/usr/bin/env python3
"""Готовит очередь постов для публикации через GitHub Actions.

Экономия обращений к модели:
  1. Предфильтр по заголовку - шум отсеивается бесплатно, до вызова LLM.
  2. Кэш извлечений в таблице ved_extractions - один материал
     разбирается моделью один раз, дальше берётся готовое.

Использование:
    docker compose run --rm -v /root/dayfacto/outbox:/app/outbox \\
        ingestion python tools/build_outbox.py --limit 20 --max-posts 3
"""

import argparse
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text                              # noqa: E402

from db.models import RawItemModel, SourceModel          # noqa: E402
from db.session import get_session                       # noqa: E402
from llm_provider import build_default_router            # noqa: E402
from tools.topical import topical_skip
from tools.autogate import risky
from ranking.scorers.ved_extract import extract          # noqa: E402
from services.editorial.ved_generator import generate    # noqa: E402

OUT = pathlib.Path(os.environ.get("OUTBOX_PATH", "/app/outbox/pending.json"))

DDL = text("""
CREATE TABLE IF NOT EXISTS ved_extractions (
    raw_item_id UUID PRIMARY KEY,
    payload     JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")

# --- Предфильтр: отсев до обращения к модели -------------------------

# Заголовки, которые заведомо не дадут поста. Проверяется по подстроке
# в нижнем регистре. Дешевле любого вызова LLM.
# Безусловный отсев: не перебивается KEEP_PATTERNS.
HARD_SKIP = [
    "личного пользования", "физическими лицами", "физических лиц",
    "пассажирской таможенной деклараци",
]

SKIP_PATTERNS = [
    # статистика и торговые обзоры
    "нарастил", "вырос", "выросл", "снизил", "сократил", "увеличил",
    "товарооборот", "заняла  место", "экспорт вырос", "импорт вырос",
    "в  раза", "по итогам полугодия",
    # разговоры, встречи, мнения
    "обсудил", "заявил", "отметил", "рассказал", "выступил",
    "провёл встречу", "провел встречу", "переговоры", "интервью",
    "мнение", "прокомментировал", "призвал", "предложил",
    # мероприятия
    "вебинар", "конференц", "форум", "семинар", "выставк", "круглый стол",
    # правоохранительная хроника без нормы
    "задержан", "изъят", "уничтожил", "пресёк", "пресек", "контрабанд",
    "возбуждено дело", "нашли", "обнаружил",
    # оперативная статистика таможен
    "за сутки оформил", "оформила около", "оформлено",
]

# Если в заголовке есть это - пропускаем даже при совпадении выше:
# нормативные признаки перевешивают.
KEEP_PATTERNS = [
    "вступает в силу", "вступают в силу", "с  года", "утвержден",
    "утверждён", "внесены изменения", "установлена ставка",
    "установлены ставки", "запрет", "ограничен", "введен", "введён",
    "порядок", "требовани", "классификатор", "перечень", "решение",
    "постановление", "приказ", "закон",
]


def prefilter(title: str) -> str:
    """Возвращает причину отсева или пустую строку."""
    low = re.sub(r"\d+", " ", title.lower())
    for h in HARD_SKIP:
        if h in low:
            return "предфильтр: %s" % h
    for k in KEEP_PATTERNS:
        if k in low:
            return ""
    for p in SKIP_PATTERNS:
        if p in low:
            return "предфильтр: %s" % p
    return ""


# --- Кэш извлечений --------------------------------------------------

def cached_extract(session, router, item_id, title, body) -> dict:
    row = session.execute(
        text("SELECT payload FROM ved_extractions WHERE raw_item_id = :i"),
        {"i": item_id},
    ).first()
    if row:
        data = row[0]
        if isinstance(data, str):
            data = json.loads(data)
        data["_cached"] = True
        return data

    change = extract(router, title, body)
    if not (change.get("what") or "").strip():
        change["_cached"] = False
        return change
    session.execute(
        text("INSERT INTO ved_extractions (raw_item_id, payload) "
             "VALUES (:i, CAST(:p AS JSONB)) ON CONFLICT DO NOTHING"),
        {"i": item_id, "p": json.dumps(change, ensure_ascii=False)},
    )
    session.commit()
    change["_cached"] = False
    return change


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--max-posts", type=int, default=4)
    ap.add_argument("--no-cache", action="store_true",
                    help="игнорировать кэш (после правки промпта)")
    a = ap.parse_args()

    session = get_session()
    session.execute(DDL)
    session.commit()

    if a.no_cache:
        session.execute(text("DELETE FROM ved_extractions"))
        session.commit()
        print("кэш извлечений очищен")

    items = (
        session.query(RawItemModel)
        .join(SourceModel)
        .filter(SourceModel.name.in_(['Гарант','КонсультантПлюс','Право.ру']) |
                SourceModel.name.like('Альта%') |
                SourceModel.name.like('SeaNews%') |
                SourceModel.name.like('LogiRus%') |
                SourceModel.name.like('ФТС%'))
        .order_by(SourceModel.weight.desc(),
                  RawItemModel.published_at.desc())
        .limit(a.limit)
        .all()
    )
    rows = [(i.id, i.title, i.body or "", i.url or "", i.source.name) for i in items]

    if not rows:
        print("материалов нет")
        session.close()
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text() or "[]")
        except json.JSONDecodeError:
            existing = []
    seen = {p.get("item_id") for p in existing}

    sent_file = OUT.parent / "sent.json"
    if sent_file.exists():
        try:
            seen |= {e.get("item_id") for e in
                     json.loads(sent_file.read_text() or "[]")}
        except json.JSONDecodeError:
            pass

    router = build_default_router()
    ready, held, skipped, cached, llm_calls = [], [], 0, 0, 0

    for item_id, title, body, url, src_name in rows:
        if len(ready) >= a.max_posts:
            break
        reason = topical_skip(src_name, title, body) or prefilter(title)
        if reason:
            skipped += 1
            print("- %s (%s)" % (title[:46], reason))
            continue

        if 'рассчитанн' in title.lower() or title[:9].count('.') == 2:
            import re as _re
            if not _re.search(r'\d+[.,]?\d*\s*(%|дол|руб|евро|проц)', title):
                print('- %s (нет цифры ставки)' % title[:46])
                continue
        change = cached_extract(session, router, item_id, title, body)
        if change.get("_cached"):
            cached += 1
        else:
            llm_calls += 1

        if str(item_id) in seen:
            continue

        if not change.get("publishable"):
            print("- %s (%s)" % (title[:46], change.get("reason", "")[:40]))
            continue

        draft = generate(router, change, source_url=url, source_text=body)
        llm_calls += 1
        if not draft.ok:
            print("- брак: %s (%s)" % (title[:40], "; ".join(draft.problems)[:50]))
            continue

        _post = {"title": draft.headline, "text": draft.render()}
        _hold = risky(_post, change, body)
        if _hold:
            held.append({"title": draft.headline, "reason": _hold})
            print("~ отложен: %s (%s)" % (draft.headline[:44], _hold))
            continue

        ready.append({
            "item_id": str(item_id),
            "title": title[:200],
            "text": draft.render(),
            "doc_number": change.get("doc_number", ""),
            "effective_date": change.get("effective_date", ""),
        })
        session.execute(
            text("UPDATE ved_extractions SET payload = "
                 "jsonb_set(payload, '{headline}', to_jsonb(CAST(:h AS text))) "
                 "WHERE raw_item_id = :i"),
            {"h": draft.headline, "i": item_id},
        )
        session.commit()
        print("+ готов: %s" % draft.headline[:58])

    session.close()

    print("\nотсеяно предфильтром: %d | из кэша: %d | обращений к LLM: %d"
          % (skipped, cached, llm_calls))

    if held:
        pathlib.Path(OUT.parent / "held.json").write_text(
            json.dumps(held, ensure_ascii=False, indent=2), encoding="utf-8")
        print("отложено (не подтверждено источником): %d" % len(held))

    if not ready:
        print("готовых постов нет")
        return 0

    OUT.write_text(json.dumps(existing + ready, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("в очереди: %d пост(ов)" % len(existing + ready))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
