"""Контекст сюжета для поста: хронология и статус."""
from sqlalchemy import text

MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря")


def _d(dt):
    try:
        return "%d %s" % (dt.day, MONTHS[dt.month - 1])
    except Exception:
        return ""


def subject_context(session, raw_item_id):
    """Возвращает dict с историей сюжета или None."""
    row = session.execute(text(
        "SELECT s.id, s.title, s.trust, s.effect, s.stage, s.items_count, "
        "s.sources_count FROM ved_subjects s "
        "JOIN ved_subject_items i ON i.subject_id = s.id "
        "WHERE i.raw_item_id = :r LIMIT 1"), {"r": str(raw_item_id)}).first()
    if not row:
        return None
    sid, title, trust, effect, stage, items, srcs = row
    if items < 2:
        return None

    hist = session.execute(text(
        "SELECT DISTINCT ON (v.payload->>'effective_date') "
        "  v.payload->>'effective_date', left(v.payload->>'what', 90) "
        "FROM ved_subject_items i "
        "JOIN ved_extractions v ON v.raw_item_id = i.raw_item_id "
        "WHERE i.subject_id = :s "
        "  AND coalesce(v.payload->>'effective_date','') <> '' "
        "ORDER BY 1"), {"s": str(sid)}).all()

    return {"id": str(sid), "title": title, "trust": float(trust or 0),
            "effect": float(effect or 0), "stage": stage,
            "items": items, "sources": srcs,
            "history": [(d, w) for d, w in hist if d]}


def render_context(ctx, current_date=""):
    """Строки для поста: подтверждения и хронология."""
    if not ctx:
        return []
    out = []

    if ctx["sources"] >= 2:
        out.append("▪ Подтверждено источниками: %d" % ctx["sources"])

    if len(ctx["history"]) >= 2 and ctx["items"] >= 3:
        out.append("")
        out.append("<b>Как менялось требование</b>")
        for date_iso, what in ctx["history"][:4]:
            try:
                y, m, dd = date_iso.split("-")
                label = "%d %s" % (int(dd), MONTHS[int(m) - 1])
            except Exception:
                continue
            mark = " ← сейчас" if date_iso == current_date else ""
            w = (what or "").strip().rstrip(".")
            if len(w) > 72:
                w = w[:72].rsplit(" ", 1)[0] + "…"
            out.append("%s — %s%s" % (label, w, mark))
    return out


SCALARS = ("scope", "goods", "value_old", "value_new", "doc_number",
           "impact_note", "date_raw")


def merge_subject_facts(session, raw_item_id, change, body):
    """Дополняет факты из соседних материалов того же сюжета."""
    from sqlalchemy import text as _t
    rows = session.execute(_t(
        "SELECT v.payload, coalesce(r.body,'') "
        "FROM ved_subject_items i "
        "JOIN ved_subject_items j ON j.subject_id = i.subject_id "
        "JOIN ved_extractions v ON v.raw_item_id = j.raw_item_id "
        "JOIN raw_items r ON r.id = j.raw_item_id "
        "WHERE i.raw_item_id = :r AND j.raw_item_id <> :r"),
        {"r": str(raw_item_id)}).all()
    if not rows:
        return change, body

    import json as _j
    out = dict(change)
    extra = [body or ""]
    filled = []
    for payload, sib_body in rows:
        sib = _j.loads(payload) if isinstance(payload, str) else payload
        if sib_body:
            extra.append(sib_body)
        for k in SCALARS:
            cur = (out.get(k) or "").strip()
            new = (sib.get(k) or "").strip()
            if not cur and new:
                out[k] = new
                filled.append(k)
            elif cur and new and len(new) > len(cur) * 1.4:
                out[k] = new
                filled.append(k + "+")
        if not out.get("tnved_codes") and sib.get("tnved_codes"):
            out["tnved_codes"] = sib["tnved_codes"]
    out["_merged_from"] = len(rows)
    out["_filled"] = filled
    return out, "\n\n".join(extra)
