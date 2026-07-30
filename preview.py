"""Предпросмотр постов: что канал опубликовал бы прямо сейчас.

Это не editorial-сервис, а разовый прогон для оценки тона и формата.
Ничего не сохраняет и никуда не отправляет.
"""

import os, sys
from sqlalchemy import create_engine, text

sys.path.insert(0, "/app")
from llm_provider import LLMRequest, LLMError, LLMParseError, build_default_router
from ranking.engine import RankingEngine
from ranking.scorers import StoryText

SCHEMA = {
    "type": "object",
    "required": ["headline", "body", "why_it_matters"],
    "properties": {
        "headline": {"type": "string"},
        "body": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "hashtags": {"type": "array"},
    },
}

SYSTEM = """Ты - редактор Telegram-канала @DayFacto.
Канал публикует только то, что реально меняет жизнь людей.

Тон: сдержанный, фактологичный. Как у информагентства, не как у блогера.
Запрещено: кликбейт, восклицательные знаки, КАПС, обороты "важно отметить",
"как сообщается", "в мире, где". Никаких выдуманных фактов и цифр.

Заголовок - законченная мысль, до 80 символов.
Тело - 2-3 предложения по существу.
why_it_matters - одно предложение: кого и как это коснётся.
Если последствий для обычных людей нет - верни why_it_matters пустой строкой.

Ответь одним JSON-объектом, без markdown:
{"headline": "...", "body": "...", "why_it_matters": "...", "hashtags": ["..."]}"""


def main():
    router = build_default_router()
    db = create_engine(os.environ["DATABASE_URL"])

    with db.connect() as conn:
        rows = list(conn.execute(text("""
            SELECT s.id, s.canonical_title,
                   (SELECT r.body FROM story_items si JOIN raw_items r ON r.id = si.raw_item_id
                    WHERE si.story_id = s.id LIMIT 1)
            FROM stories s ORDER BY s.id DESC LIMIT 40
        """)))

    cands = [StoryText(r[0], r[1] or "") for r in rows]
    bodies = {r[0]: (r[2] or "")[:1500] for r in rows}

    ranked = RankingEngine(router=router).score_batch(cands, [])
    top = [r for r in ranked if r.decision == "publish"][:3]

    if not top:
        print("Нет сюжетов, прошедших в публикацию.")
        return

    for i, r in enumerate(top, 1):
        print("\n" + "=" * 70)
        print(f"ПОСТ {i}   балл {r.final_score:.2f}   тема: {r.topic}")
        print("=" * 70)
        req = LLMRequest(
            system=SYSTEM,
            user=f"{r.title}\n\n{bodies.get(r.story_id, '')}",
            json_schema=SCHEMA, temperature=0.3, max_tokens=700,
        )
        # Тот же принцип, что в классификации: основной провайдер часто
        # отказывается писать про политику, поэтому перебираем всех.
        resp, err = None, None
        primary = router._resolve("editorial").name
        for name in [primary] + [n for n in router.providers if n != primary]:
            try:
                resp = router.providers[name].generate(req)
                break
            except (LLMError, LLMParseError) as e:
                err = e
        try:
            if resp is None:
                raise err
            d = resp.data
            print(f"\n**{d['headline']}**\n")
            print(d["body"])
            if d.get("why_it_matters"):
                print(f"\n> {d['why_it_matters']}")
            if d.get("hashtags"):
                print("\n" + " ".join("#" + h for h in d["hashtags"][:3]))
            print(f"\n[{resp.provider}, {resp.total_tokens} токенов]")
        except (LLMError, LLMParseError) as e:
            print(f"\nне удалось сгенерировать: {type(e).__name__}")


if __name__ == "__main__":
    main()
