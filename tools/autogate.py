import json

RISK = ("штраф", "ответственност", "наказан", "приложени", "перечн",
        "отказ", "задержк", "изъяти", "конфискац", "аннулиров",
        "взыскан", "пени", "административн")

EVENT = ("конференци", "сесси", "саммит", "выставк", "форум", "чемпионат",
         "олимпиад", "фестивал", "cop 1", "cop 2", "соревновани", "съезд")

ONE_COUNTRY = ("в армению", "в армении", "в казахстан", "в казахстане",
               "в киргизию", "в киргизии", "в кыргызстан", "в беларусь",
               "в белоруссию", "в республику армения")


def _no_source(text, facts, words):
    for w in words:
        if w in text and w not in facts:
            return w
    return None


def risky(post, change, source=""):
    t = " ".join([post.get("title") or "", post.get("text") or ""]).lower()
    hard = {k: v for k, v in change.items()
            if k not in ("impact_note", "what", "reason", "problems")}
    facts = (json.dumps(hard, ensure_ascii=False) + " " + (source or "")).lower()

    w = _no_source(t, facts, RISK)
    if w:
        return "утверждение вне источника: %s" % w

    if change.get("date_status") != "exact":
        return "дата не подтверждена дословно"

    if change.get("change_type") in ("control", "procedure") \
            and not (change.get("scope") or "").strip():
        return "не извлечён охват требования"

    for w in EVENT:
        if w in t:
            return "разовое мероприятие: %s" % w

    for w in ONE_COUNTRY:
        if w in t and "еаэс" not in t.split(w)[0][-120:]:
            return "касается одной страны: %s" % w.strip()

    return None


def strip_unsupported(text, change, source=""):
    """Убирает предложения с утверждениями, которых нет в источнике."""
    import re as _re
    import json as _j
    hard = {k: v for k, v in change.items()
            if k not in ("impact_note", "what", "reason", "problems")}
    facts = (_j.dumps(hard, ensure_ascii=False) + " " + (source or "")).lower()
    keep = []
    for sent in _re.split(r"(?<=[.!?])\s+", text or ""):
        low = sent.lower()
        if not any(w in low and w not in facts for w in RISK):
            keep.append(sent)
    res = " ".join(keep).strip()
    res = _re.sub(r"\s+([,.;])", r"\1", res)
    res = res.rstrip(" .,;")
    tail = _re.compile(
        r"[,;]?\s+(за|и|или|в|во|с|со|на|по|к|от|до|при|для|из|о|об|а|но)$",
        _re.I)
    for _ in range(3):
        m = tail.search(res)
        if not m:
            break
        res = res[:m.start()].rstrip(" .,;")
    if res and res[-1] not in ".!?":
        res += "."
    return res
