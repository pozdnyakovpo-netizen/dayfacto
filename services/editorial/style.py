import html
import re

MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря")

CODE = re.compile(r"\b(\d{4}\s?\d{2}\s?\d{3}\s?\d)\b|№\s?([\d/-]+[-\w]*)")


def esc(t):
    return html.escape(t or "", quote=False)


def ru_date(iso):
    try:
        y, m, d = iso.split("-")
        return "%d %s %s" % (int(d), MONTHS[int(m) - 1], y)
    except Exception:
        return ""


def mono(text):
    """Коды ТН ВЭД и номера документов - моноширинным."""
    def rep(m):
        return "<code>%s</code>" % m.group(0)
    return CODE.sub(rep, text)


def _para(text, limit=None):
    t = re.sub(r"\s+", " ", (text or "").strip())
    if limit and len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0] + "…"
    return t


def build_post(d):
    """Элитный шаблон: сильный заголовок, дата, воздух, моно-реквизиты."""
    head = _para(getattr(d, "headline", ""))
    head = head.rstrip(":.")
    out = ["<b>%s</b>" % esc(head)]

    eff = ru_date(getattr(d, "effective_date", "") or "")
    if eff:
        out += ["", "▪ Вступает в силу %s" % eff]

    lead = _para(getattr(d, "what_changes", ""))
    if lead:
        out += ["", mono(esc(lead))]

    who = _para(getattr(d, "who", ""))
    if who:
        out += ["", "<b>Кого касается</b>", mono(esc(who))]

    todo = _para(getattr(d, "what_to_do", ""))
    if todo:
        out += ["", "<b>Что делать</b>", mono(esc(todo))]

    src = getattr(d, "source_line", "") or ""
    m = re.search(r"https?://\S+", src)
    name = re.sub(r"^Источник:\s*", "", src)
    name = re.sub(r"\s*[—-]?\s*https?://\S+", "", name).strip(" .—-")
    if m:
        tail = "%s · <a href=\"%s\">документ</a>" % (esc(name or "Источник"),
                                                     esc(m.group(0)))
    else:
        tail = esc(name)
    if tail.strip():
        out += ["", tail]

    return "\n".join(out).strip()
