import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from db.session import get_session
from services.editorial.trois import parse, build
from services.editorial.cover import trois_cover

OUT = pathlib.Path(os.environ.get("OUTBOX_PATH", "/app/outbox/pending.json"))

s = get_session()
row = s.execute(text(
    "SELECT r.id, r.title, r.body, r.url FROM raw_items r "
    "JOIN sources s ON s.id = r.source_id "
    "WHERE r.title LIKE 'Изменения с%' AND s.name LIKE 'ТГ — Альта%' "
    "ORDER BY r.published_at DESC NULLS LAST LIMIT 1")).first()
s.close()

if not row:
    print("нет материалов ТРОИС")
    raise SystemExit(0)

rid, title, body, url = row
data = parse(body or "")
if not data:
    print("не разобрался формат")
    raise SystemExit(0)

head, txt = build(data)
if not txt:
    print("нечего публиковать")
    raise SystemExit(0)

n_freed = len(data["removed"]) + len(data["expired"])
cov = ""
try:
    cov = trois_cover(data["period"], len(data["added"]), n_freed)
except Exception as e:
    print("(обложка не собрана: %s)" % str(e)[:80])

queue = json.loads(OUT.read_text(encoding="utf-8") or "[]") if OUT.exists() else []
queue.append({"item_id": "trois-%s" % str(rid), "title": head, "text": txt,
              "cover": cov, "change_type": "", "doc_number": "",
              "effective_date": ""})
OUT.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
print("+", head)
print("добавлено: %d, снято: %d" % (len(data["added"]), n_freed))
