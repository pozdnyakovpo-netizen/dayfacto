from __future__ import annotations

import argparse
import logging
import os
import sys

from sqlalchemy import create_engine, text

from .engine import RankingEngine
from .scorers import StoryText

# Отбор кандидатов взвешен по источнику: вес в таблице sources до сих
# пор не использовался, и лента ТАСС забивала выдачу объёмом. Теперь
# сюжет из «Российской газеты» (вес 1.6) обходит военную сводку (0.5)
# ещё до обращения к модели — это и дешевле, и ближе к концепции канала.
SQL_CANDIDATES = text("""
    SELECT s.id, s.canonical_title,
           max(src.weight) AS w, count(si.raw_item_id) AS items
    FROM stories s
    LEFT JOIN story_items si ON si.story_id = s.id
    LEFT JOIN raw_items r ON r.id = si.raw_item_id
    LEFT JOIN sources src ON src.id = r.source_id
    GROUP BY s.id, s.canonical_title
    ORDER BY w DESC NULLS LAST, items DESC, s.id DESC
    LIMIT :limit
""")

SQL_PUBLISHED = text("""
    SELECT s.id, s.canonical_title
    FROM stories s
    JOIN drafts d ON d.story_id = s.id
    JOIN publish_log p ON p.draft_id = d.id
""")

SQL_UPSERT = text("""
    INSERT INTO scores (story_id, relevance, novelty, dup_risk, final_score, computed_at)
    VALUES (:story_id, :relevance, :novelty, :dup_risk, :final_score, now())
""")


def _fetch(conn, sql, **params):
    return [StoryText(r[0], r[1] or "") for r in conn.execute(sql, params)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    router = None
    if not args.no_llm:
        from llm_provider import build_default_router
        router = build_default_router()

    engine_db = create_engine(os.environ["DATABASE_URL"])
    ranker = RankingEngine(router=router)

    with engine_db.connect() as conn:
        candidates = _fetch(conn, SQL_CANDIDATES, limit=args.limit)
        try:
            published = _fetch(conn, SQL_PUBLISHED)
        except Exception:
            published = []

    if not candidates:
        print("Сюжетов не найдено.")
        return 1

    print(f"\nОценка {len(candidates)} сюжетов (опубликовано: {len(published)}, LLM: {'нет' if args.no_llm else 'да'})\n")
    results = ranker.score_batch(candidates, published)

    marks = {"publish": "OK", "moderate": "MOD", "hold": "HLD", "drop": "DEL"}
    print(f"{'':4} {'score':>6} {'rel':>5} {'nov':>5} {'dup':>5}  заголовок")
    print("-" * 100)
    for r in results:
        print(f"{marks.get(r.decision, '?'):4} {r.final_score:6.3f} {r.relevance:5.2f} {r.novelty:5.2f} {r.dup_risk:5.2f}  {r.title[:60]}")
        if r.decision in ("drop", "moderate"):
            print(f"{'':23}└─ {r.reason}")

    counts: dict[str, int] = {}
    for r in results:
        counts[r.decision] = counts.get(r.decision, 0) + 1
    print("\nИтого: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    if args.save:
        with engine_db.begin() as conn:
            for r in results:
                conn.execute(SQL_UPSERT, {
                    "story_id": r.story_id, "relevance": r.relevance,
                    "novelty": r.novelty, "dup_risk": r.dup_risk,
                    "final_score": r.final_score,
                })
        print(f"Записано в scores: {len(results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
