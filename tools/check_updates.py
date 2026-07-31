import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from db.session import get_session
from services.memory.subjects import subject_labels

s = get_session()
rows = s.execute(text(
    "SELECT sb.id, sb.title, sb.stage, sb.trust, sb.effect, "
    "p.published_at, p.message_id, max(r.fetched_at) "
    "FROM ved_subjects sb "
    "JOIN ved_subject_items i ON i.subject_id = sb.id "
    "JOIN raw_items r ON r.id = i.raw_item_id "
    "JOIN published_stories p ON p.story_id IN ("
    "  SELECT raw_item_id FROM ved_subject_items WHERE subject_id = sb.id) "
    "GROUP BY sb.id, sb.title, sb.stage, sb.trust, sb.effect, "
    "         p.published_at, p.message_id "
    "HAVING max(r.fetched_at) > p.published_at "
    "ORDER BY sb.effect DESC")).all()
print("сюжетов с обновлениями:", len(rows))

for sid, title, stage, trust, effect, pub, mid, fresh in rows:
    lab = subject_labels(stage, trust, effect)
    print("-" * 58)
    print("сюжет: %s" % (title or "")[:66])
    print("пост #%s от %s, новое от %s"
          % (mid, pub.strftime("%d.%m %H:%M"), fresh.strftime("%d.%m %H:%M")))
    print("%s | надёжность: %s | %s"
          % (lab["status"], lab["reliability"], lab["impact"]))
    for t, in s.execute(text(
            "SELECT left(r.title, 66) FROM ved_subject_items i "
            "JOIN raw_items r ON r.id = i.raw_item_id "
            "WHERE i.subject_id = :s AND r.fetched_at > :p "
            "ORDER BY r.fetched_at DESC LIMIT 3"),
            {"s": str(sid), "p": pub}):
        print("  + %s" % t)
s.close()
