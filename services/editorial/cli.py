"""Генерация постов по лучшим сюжетам.

    python -m services.editorial.cli --limit 5
    python -m services.editorial.cli --limit 5 --min-score 0.85
"""

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

SQL = text("""
    SELECT s.id, s.canonical_title,
           (SELECT r.body FROM story_items si JOIN raw_items r ON r.id = si.raw_item_id
            WHERE si.story_id = s.id ORDER BY length(coalesce(r.body,'')) DESC LIMIT 1)
    FROM stories s
    WHERE s.canonical_title IS NOT NULL
      AND EXISTS (
        SELECT 1 FROM story_items si2
        JOIN raw_items r2 ON r2.id = si2.raw_item_id
        JOIN sources src ON src.id = r2.source_id
        WHERE si2.story_id = s.id AND src.weight >= 0.9
      )
    ORDER BY s.last_updated_at DESC
    LIMIT :n
""")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=5, help="сколько постов написать")
    ap.add_argument("--pool", type=int, default=40, help="из скольких сюжетов выбирать")
    ap.add_argument("--min-score", type=float, default=0.78)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    router = build_default_router()
    db = create_engine(os.environ["DATABASE_URL"])
    with db.connect() as c:
        rows = list(c.execute(SQL, {"n": args.pool}))

    cands = [StoryText(r[0], r[1] or "") for r in rows]
    bodies = {r[0]: (r[2] or "") for r in rows}

    ranked = RankingEngine(router=router).score_batch(cands, [])
    top = [r for r in ranked if r.decision == "publish" and r.final_score >= args.min_score]

    if not top:
        print(f"Нет сюжетов с баллом >= {args.min_score}")
        return 1

    published = failed = 0
    for r in top[: args.limit]:
        d = generate(router, r.story_id, r.title, bodies.get(r.story_id, ""))
        print("\n" + "─" * 66)
        if not d.headline:
            print(f"НЕ НАПИСАН  {r.title[:56]}\n  причина: {'; '.join(d.problems)}")
            failed += 1
            continue
        print(d.render())
        print(f"\n  [{d.provider}, {d.tokens} токенов, балл {r.final_score:.2f}]")
        if d.ok:
            published += 1
        else:
            print(f"  НА МОДЕРАЦИЮ: {'; '.join(d.problems)}")

    print("\n" + "─" * 66)
    print(f"готовы к публикации {published}, на модерацию {len(top[:args.limit]) - published - failed}, "
          f"не написаны {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
