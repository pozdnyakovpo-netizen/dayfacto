import os, requests
from sqlalchemy import create_engine, text

DB = create_engine(os.environ["DATABASE_URL"])
TOK = os.environ["TELEGRAM_BOT_TOKEN"]
ADMIN = os.environ["TELEGRAM_ADMIN_CHAT_ID"]
P = []

with DB.connect() as c:
    rows = c.execute(text(
        "SELECT s.name, count(r.id) FROM sources s "
        "LEFT JOIN raw_items r ON r.source_id=s.id "
        "AND r.fetched_at > now() - interval '36 hours' "
        "WHERE s.active GROUP BY s.name HAVING count(r.id)=0")).all()
    for n, _ in rows:
        P.append("молчит 36ч: %s" % n)

    n = c.execute(text("SELECT count(*) FROM published_stories "
                       "WHERE published_at > now() - interval '72 hours'")).scalar()
    if not n:
        P.append("нет публикаций 72ч")

    n = c.execute(text("SELECT count(*) FROM raw_items "
                       "WHERE fetched_at > now() - interval '24 hours'")).scalar()
    if not n:
        P.append("сутки без новых материалов")

if P:
    requests.post("https://api.telegram.org/bot%s/sendMessage" % TOK,
                  json={"chat_id": ADMIN, "text": "DayFacto, замечания:\n— " + "\n— ".join(P)},
                  timeout=30)
    print("отправлено замечаний:", len(P))
else:
    print("замечаний нет")
