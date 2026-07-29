from __future__ import annotations

import argparse
import logging
import os
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, "/app")
from llm_provider import build_default_router
from ranking.engine import RankingEngine
from ranking.scorers import StoryText
from services.editorial.generator import generate
from services.publisher.telegram_client import TelegramClient, TelegramError

SQL_POOL = text("""
    SELECT s.id, s.canonical_title,
           (SELECT r.body FROM story_items si JOIN raw_items r ON r.id = si.raw_item_id
            WHERE si.story_id = s.id ORDER BY length(coalesce(r.body,'')) DESC LIMIT 1)
    FROM stories s
    WHERE s.canonical_title IS NOT NULL
      AND EXISTS (
        SELECT 1 FROM story_items si2
        JOIN raw_items r2 ON r2.id = si2.raw_item_id
        JOIN sources src ON src.id = r2.source_id
        WHERE si2.story_id = s.id AND src.weight >= 0.9)
    ORDER BY s.last_updated_at DESC
    LIMIT :n
""")

DDL = text("""
    CREATE TABLE IF NOT EXISTS published_stories (
        story_id     uuid PRIMARY KEY,
        message_id   bigint,
        chat_id      text,
        headline     text,
        published_at timestamptz DEFAULT now()
    )
""")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--pool", type=int, default=30)
    ap.add_argument("--min-score", type=float, default=0.85)
    ap.add_argument("--to-admin", action="store_true")
    ap.add_argument("--to-channel", action="store_true")
    a = ap.parse_args()

    logging.basicConfig(level=logging.INFO)

    chat = None
    if a.to_channel:
        chat = os.environ.get("TELEGRAM_CHANNEL_ID")
    elif a.to_admin:
        chat = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")
    if (a.to_channel or a.to_admin) and not chat:
        print("нужный chat_id не задан в .env")
        return 1

    tg = None
    if chat:
        tg = TelegramClient()
        print(f"бот @{tg.me()} -> {chat}\n")

    db = create_engine(os.environ["DATABASE_URL"])
    with db.begin() as c:
        c.execute(DDL)
    with db.connect() as c:
        rows = list(c.execute(SQL_POOL, {"n": a.pool}))
        done = {r[0] for r in c.execute(text("SELECT story_id FROM published_stories"))}

    rows = [r for r in rows if r[0] not in done]
    if not rows:
        print("нет новых сюжетов")
        return 0

    router = build_default_router()
    ranked = RankingEngine(router=router).score_batch(
        [StoryText(r[0], r[1] or "") for r in rows], [])
    bodies = {r[0]: (r[2] or "") for r in rows}
    top = [r for r in ranked if r.decision == "publish" and r.final_score >= a.min_score]

    sent = held = 0
    for r in top:
        if sent >= a.limit:
            break
        d = generate(router, r.story_id, r.title, bodies.get(r.story_id, ""))
        if not d.ok:
            held += 1
            print(f"[отложен] {(d.headline or r.title)[:56]}")
            print(f"          {'; '.join(d.problems)}\n")
            continue

        print("-" * 64)
        print(d.render())
        print(f"  [{d.provider}, балл {r.final_score:.2f}]")

        if tg:
            try:
                mid = tg.send(chat, d.render())
                with db.begin() as c:
                    c.execute(text(
                        "INSERT INTO published_stories "
                        "(story_id, message_id, chat_id, headline) "
                        "VALUES (:s,:m,:c,:h) ON CONFLICT (story_id) DO NOTHING"),
                        {"s": r.story_id, "m": mid, "c": str(chat), "h": d.headline})
                print(f"  ОТПРАВЛЕНО, message_id={mid}")
            except TelegramError as exc:
                print(f"  ОШИБКА ОТПРАВКИ: {exc}")
                break
        else:
            print("  (черновик, никуда не отправлен)")
        sent += 1
        print()

    print(f"\nитого: отправлено {sent}, отложено {held}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
