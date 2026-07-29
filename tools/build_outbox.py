#!/usr/bin/env python3
"""Готовит очередь постов для публикации через GitHub Actions.

Запускается на сервере. Берёт свежие материалы из базы, прогоняет
через извлечение и генерацию, складывает готовые посты в
outbox/pending.json. Дальше их забирает workflow publish.yml.

Использование:
    docker compose run --rm ingestion python tools/build_outbox.py --limit 20
    git add outbox/pending.json && git commit -m "outbox" && git push
"""

import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, "/app")

from db.models import RawItemModel, SourceModel          # noqa: E402
from db.session import get_session                       # noqa: E402
from llm_provider import build_default_router            # noqa: E402
from ranking.scorers.ved_extract import extract          # noqa: E402
from services.editorial.ved_generator import generate    # noqa: E402

OUT = pathlib.Path(os.environ.get("OUTBOX_PATH", "/app/outbox/pending.json"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20,
                    help="сколько материалов просмотреть")
    ap.add_argument("--max-posts", type=int, default=4,
                    help="сколько постов положить в очередь")
    a = ap.parse_args()

    session = get_session()
    try:
        items = (
            session.query(RawItemModel)
            .join(SourceModel)
            .filter(SourceModel.name.like("Альта%"))
            .order_by(SourceModel.weight.desc(), RawItemModel.published_at.desc())
            .limit(a.limit)
            .all()
        )
        rows = [(str(i.id), i.title, i.body or "", i.url or "") for i in items]
    finally:
        session.close()

    if not rows:
        print("новых материалов нет")
        return 0

    router = build_default_router()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text() or "[]")
        except json.JSONDecodeError:
            existing = []
    seen = {p.get("item_id") for p in existing}

    ready = []
    for item_id, title, body, url in rows:
        if len(ready) >= a.max_posts:
            break
        if item_id in seen:
            continue
        change = extract(router, title, body)
        if not change.get("publishable"):
            print("- пропуск: %s (%s)" % (title[:50], change.get("reason", "")))
            continue
        draft = generate(router, change, source_url=url)
        if not draft.ok:
            print("- брак: %s (%s)" % (title[:50], "; ".join(draft.problems)))
            continue
        ready.append({
            "item_id": item_id,
            "title": title[:200],
            "text": draft.render(),
            "doc_number": change.get("doc_number", ""),
            "effective_date": change.get("effective_date", ""),
        })
        print("+ готов: %s" % draft.headline[:60])

    if not ready:
        print("готовых постов нет")
        return 0

    OUT.write_text(
        json.dumps(existing + ready, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("\nв очереди: %d пост(ов) -> %s" % (len(existing + ready), OUT))
    print("дальше: git add outbox/pending.json && git commit -m outbox && git push")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
