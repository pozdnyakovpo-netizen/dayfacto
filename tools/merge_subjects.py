import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from db.session import get_session
from services.memory.subjects import fingerprint, similarity

MERGE_SIM = 0.28
s = get_session()

rows = s.execute(text(
    "SELECT sb.id, sb.title, sb.items_count, "
    "coalesce(string_agg(v.payload->>'what', ' '), '') "
    "FROM ved_subjects sb "
    "LEFT JOIN ved_subject_items i ON i.subject_id = sb.id "
    "LEFT JOIN ved_extractions v ON v.raw_item_id = i.raw_item_id "
    "GROUP BY sb.id, sb.title, sb.items_count "
    "ORDER BY sb.items_count DESC")).all()
print("сюжетов до слияния:", len(rows))

pool, merged = [], 0
for sid, ttl, cnt, whats in rows:
    fp = fingerprint(ttl, whats)
    hit = None
    for p in pool:
        if similarity(fp, p["fp"]) >= MERGE_SIM:
            hit = p
            break
    if hit is None:
        pool.append({"id": sid, "fp": fp})
        continue
    s.execute(text(
        "UPDATE ved_subject_items SET subject_id=:k WHERE subject_id=:o "
        "AND raw_item_id NOT IN (SELECT raw_item_id FROM ved_subject_items "
        "WHERE subject_id=:k)"), {"k": hit["id"], "o": sid})
    s.execute(text("DELETE FROM ved_subject_items WHERE subject_id=:o"), {"o": sid})
    s.execute(text("UPDATE ved_subject_events SET subject_id=:k WHERE subject_id=:o"),
              {"k": hit["id"], "o": sid})
    s.execute(text("DELETE FROM ved_subjects WHERE id=:o"), {"o": sid})
    hit["fp"] |= fp
    merged += 1

s.execute(text(
    "UPDATE ved_subjects sb SET items_count = x.c FROM "
    "(SELECT subject_id, count(*) c FROM ved_subject_items GROUP BY 1) x "
    "WHERE x.subject_id = sb.id"))
s.commit()
s.close()
print("склеено:", merged, "| осталось:", len(pool))

s2 = get_session()
s2.execute(text(
    "UPDATE ved_subjects sb SET sources_count = x.c FROM "
    "(SELECT i.subject_id, count(DISTINCT split_part(s.name,'—',1)) c "
    " FROM ved_subject_items i JOIN raw_items r ON r.id=i.raw_item_id "
    " JOIN sources s ON s.id=r.source_id GROUP BY 1) x "
    "WHERE x.subject_id = sb.id"))
s2.commit()
s2.close()
print("источники пересчитаны")
