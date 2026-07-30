import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from db.session import get_session
from services.memory.subjects import (doc_key, fingerprint, similarity,
                                      slugify, trust_index, effect_index)

STAGE_BY = {"draft": "draft", "adopted": "adopted",
            "published": "adopted", "in_force": "in_force"}
SIM = 0.28

s = get_session()
rows = s.execute(text("""
    SELECT v.raw_item_id, v.payload, r.title, coalesce(r.body,''),
           r.url, src.name, r.published_at
    FROM ved_extractions v
    JOIN raw_items r ON r.id = v.raw_item_id
    JOIN sources src ON src.id = r.source_id
    ORDER BY r.published_at NULLS LAST
""")).all()

subjects = []
linked = 0

for _sid, _dk, _ttl in s.execute(text(
        "SELECT id, coalesce(doc_key,''), title FROM ved_subjects")).all():
    _fp = fingerprint(_ttl)
    for _w, in s.execute(text(
            "SELECT coalesce(v.payload->>'what','') || ' ' || "
            "coalesce(v.payload->>'scope','') "
            "FROM ved_subject_items i "
            "JOIN ved_extractions v ON v.raw_item_id = i.raw_item_id "
            "WHERE i.subject_id = :i"), {"i": _sid}).all():
        _fp |= fingerprint(_w)
    subjects.append({"id": _sid, "doc_key": _dk, "fp": _fp,
                     "sources": [], "changes": []})
print("загружено сюжетов из базы:", len(subjects))

for rid, payload, title, body, url, srcname, pub in rows:
    ch = json.loads(payload) if isinstance(payload, str) else payload
    dk = doc_key(ch.get("doc_number") or "")
    fp = fingerprint(ch.get("what"), ch.get("scope"), title)

    match = None
    for sub in subjects:
        if dk and sub["doc_key"] and dk == sub["doc_key"]:
            match = sub
            break
        if similarity(fp, sub["fp"]) >= SIM:
            match = sub
            break

    if match is None:
        head = (ch.get("what") or title or "")[:200]
        sid = s.execute(text(
            "INSERT INTO ved_subjects (slug, title, doc_key, effective_date) "
            "VALUES (:s, :t, :d, CAST(NULLIF(:e,'') AS date)) "
            "ON CONFLICT (slug) DO UPDATE SET last_seen = now() RETURNING id"),
            {"s": slugify(head)[:80] + "-" + str(rid)[:8], "t": head,
             "d": dk or None, "e": ch.get("effective_date") or ""}).scalar()
        match = {"id": sid, "doc_key": dk, "fp": set(fp),
                 "sources": [], "changes": []}
        subjects.append(match)
        s.execute(text("INSERT INTO ved_subject_events (subject_id, kind, note) "
                       "VALUES (:i, 'first_signal', :n)"),
                  {"i": sid, "n": (srcname or "")[:120]})
    else:
        match["fp"] |= fp
        if dk and not match["doc_key"]:
            match["doc_key"] = dk
            s.execute(text("UPDATE ved_subjects SET doc_key=:d WHERE id=:i"),
                      {"d": dk, "i": match["id"]})
        linked += 1

    match["sources"].append(srcname or "")
    match["changes"].append(ch)
    st = STAGE_BY.get(ch.get("stage") or "", "signal")
    s.execute(text(
        "INSERT INTO ved_subject_items (subject_id, raw_item_id, stage) "
        "VALUES (:s, :r, :g) ON CONFLICT DO NOTHING"),
        {"s": match["id"], "r": rid, "g": st})

s.commit()
print("сюжетов: %d, связано материалов: %d" % (len(subjects), linked))

# --- индексы доверия и эффекта, стадия ------------------------------
STAGE_ORDER = ["signal", "draft", "adopted", "in_force",
               "clarified", "amended", "revoked", "practice"]

for sub in subjects:
    ch_best = max(sub["changes"],
                  key=lambda c: (bool(c.get("doc_number")),
                                 c.get("date_status") == "exact",
                                 len(c.get("scope") or "")))
    trust = trust_index(ch_best, sub["sources"])
    effect = max(effect_index(c) for c in sub["changes"])

    stages = [STAGE_BY.get(c.get("stage") or "", "signal") for c in sub["changes"]]
    stage = max(stages, key=lambda x: STAGE_ORDER.index(x))

    src_uniq = len({x.split("—")[0].strip() for x in sub["sources"] if x})
    s.execute(text("""
        UPDATE ved_subjects SET
          trust = :t, effect = :e, stage = :g,
          sources_count = :sc, items_count = :ic, last_seen = now(),
          effective_date = coalesce(effective_date,
                                    CAST(NULLIF(:ed,'') AS date))
        WHERE id = :i"""),
        {"t": trust, "e": effect, "g": stage, "sc": src_uniq,
         "ic": len(sub["changes"]), "i": sub["id"],
         "ed": ch_best.get("effective_date") or ""})

s.commit()
s.close()
print("индексы посчитаны")

# --- слияние сюжетов с одним документом -----------------------------
dups = s.execute(text("""
    SELECT doc_key, array_agg(id ORDER BY items_count DESC) FROM ved_subjects
    WHERE coalesce(doc_key,'') <> '' GROUP BY doc_key HAVING count(*) > 1
""")).all()
merged = 0
for dk, ids in dups:
    keep, rest = ids[0], ids[1:]
    for old_id in rest:
        s.execute(text("UPDATE ved_subject_items SET subject_id=:k "
                       "WHERE subject_id=:o AND raw_item_id NOT IN "
                       "(SELECT raw_item_id FROM ved_subject_items WHERE subject_id=:k)"),
                  {"k": keep, "o": old_id})
        s.execute(text("UPDATE ved_subject_events SET subject_id=:k WHERE subject_id=:o"),
                  {"k": keep, "o": old_id})
        s.execute(text("DELETE FROM ved_subjects WHERE id=:o"), {"o": old_id})
        merged += 1
    s.execute(text("INSERT INTO ved_subject_events (subject_id, kind, note) "
                   "VALUES (:i, 'merged', :n)"), {"i": keep, "n": dk})
s.commit()
if merged:
    print("склеено сюжетов:", merged)
