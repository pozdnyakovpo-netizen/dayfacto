import os
import re
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 900
SS = 2

GRAPHITE = (15, 19, 24)
EMERALD = (31, 122, 90)
LIGHT = (243, 245, 244)
MUTED = (167, 178, 173)
LINE = (39, 48, 56)
AMBER = (200, 146, 46)
JADE = (45, 156, 116)
SLATE = (22, 28, 34)

FD = os.environ.get("FONTS_DIR", "/app/assets/fonts")
BRAND = "ВЭД: что меняется"

BADGE = {
    "duty_rate": "Пошлины",
    "tnved_code": "ТН ВЭД",
    "preference": "Преференции",
    "procedure": "Процедуры",
    "restriction": "Запреты",
    "control": "Контроль",
    "currency_control": "Валютный контроль",
    "court_practice": "Практика",
    "rate_info": "Ставки",
}


def _f(name, size):
    return ImageFont.truetype(os.path.join(FD, name), size * SS)


def _wrap(d, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines
    return lines


def make(headline, change_type="", effective_date="", note="",
         urgent=False, out="/app/outbox/cover.png"):
    accent = AMBER if urgent else EMERALD
    img = Image.new("RGB", (W * SS, H * SS), GRAPHITE)
    d = ImageDraw.Draw(img)
    pad = 80 * SS

    d.rectangle((pad // 2, pad // 2, W * SS - pad // 2, H * SS - pad // 2),
                outline=LINE, width=2 * SS)
    d.rectangle((pad, pad, pad + 6 * SS, pad + 96 * SS), fill=accent)

    badge = badge_for(change_type, note, headline, urgent)
    d.text((pad + 30 * SS, pad + 22 * SS), badge.upper(),
           font=_f("Inter-SemiBold.ttf", 26), fill=accent)

    fh = _f("InterDisplay-SemiBold.ttf", 66)
    y = pad + 190 * SS
    for ln in _wrap(d, headline, fh, W * SS - pad * 2 - 20 * SS)[:3]:
        d.text((pad, y), ln, font=fh, fill=LIGHT)
        y += 88 * SS

    if note:
        fn = _f("Inter-Regular.ttf", 30)
        y += 14 * SS
        for ln in _wrap(d, note, fn, W * SS - pad * 2)[:2]:
            d.text((pad, y), ln, font=fn, fill=MUTED)
            y += 44 * SS

    ly = H * SS - pad - 76 * SS
    d.line([(pad, ly), (W * SS - pad, ly)], fill=LINE, width=2 * SS)
    d.text((pad, ly + 26 * SS), effective_date or "",
           font=_f("Inter-Medium.ttf", 32), fill=LIGHT)

    fs = _f("Inter-Regular.ttf", 28)
    tw = d.textlength(BRAND, font=fs)
    d.text((W * SS - pad - tw, ly + 28 * SS), BRAND, font=fs, fill=MUTED)

    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.resize((W, H), Image.LANCZOS).save(out)
    return out


def brand(out="/app/outbox/pinned.png"):
    img = Image.new("RGB", (W * SS, H * SS), GRAPHITE)
    d = ImageDraw.Draw(img)
    pad = 90 * SS
    d.rectangle((pad // 2, pad // 2, W * SS - pad // 2, H * SS - pad // 2),
                outline=LINE, width=2 * SS)
    d.rectangle((pad, pad + 20 * SS, pad + 8 * SS, pad + 250 * SS), fill=EMERALD)
    fh = _f("InterDisplay-SemiBold.ttf", 68)
    d.text((pad + 42 * SS, pad + 18 * SS), "ВЭД:", font=fh, fill=LIGHT)
    d.text((pad + 42 * SS, pad + 100 * SS), "что меняется", font=fh, fill=LIGHT)
    fn = _f("Inter-Regular.ttf", 30)
    d.text((pad + 42 * SS, pad + 206 * SS),
           "Изменения в таможне и ВЭД — с датой и документом",
           font=fn, fill=MUTED)
    ly = H * SS - pad - 120 * SS
    d.line([(pad, ly), (W * SS - pad, ly)], fill=LINE, width=2 * SS)
    fi = _f("Inter-Medium.ttf", 26)
    x = pad
    for it in ("Ставки и коды ТН ВЭД", "Даты вступления", "Что делать бизнесу"):
        d.text((x, ly + 40 * SS), it, font=fi, fill=LIGHT)
        x += int(d.textlength(it, font=fi)) + 60 * SS
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.resize((W, H), Image.LANCZOS).save(out)
    return out


ORG_MARKERS = (
    ("ЕАЭС", ("еэк", "евразийск", "еаэс")),
    ("ФТС", ("фтс", "таможенн служб")),
    ("Правительство", ("правительств", "постановлен", "распоряжен")),
    ("Сертификация", ("сертифик", "соответств", "росаккредитац")),
    ("Логистика", ("перевозк", "транзит", "логистик", "порт")),
)


def badge_for(change_type="", doc_number="", text="", urgent=False):
    if urgent:
        return "Сроки"
    hay = ((doc_number or "") + " " + (text or "")).lower()
    org = ""
    for name, keys in ORG_MARKERS:
        if any(k in hay for k in keys):
            org = name
            break
    typ = BADGE.get(change_type, "")
    if org and typ:
        return "%s · %s" % (org, typ)
    return org or typ or "Изменение"


def _frame(d, pad, accent, badge):
    d.rectangle((pad // 2, pad // 2, W * SS - pad // 2, H * SS - pad // 2),
                outline=LINE, width=2 * SS)
    d.rectangle((pad, pad, pad + 6 * SS, pad + 96 * SS), fill=accent)
    d.text((pad + 30 * SS, pad + 26 * SS), badge.upper(),
           font=_f("Inter-SemiBold.ttf", 26), fill=accent)


def _footer(d, pad, left):
    ly = H * SS - pad - 76 * SS
    d.line([(pad, ly), (W * SS - pad, ly)], fill=LINE, width=2 * SS)
    d.text((pad, ly + 26 * SS), left or "",
           font=_f("Inter-Medium.ttf", 32), fill=LIGHT)
    fs = _f("Inter-Regular.ttf", 28)
    tw = d.textlength(BRAND, font=fs)
    d.text((W * SS - pad - tw, ly + 28 * SS), BRAND, font=fs, fill=MUTED)


def _save(img, out):
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    img.resize((W, H), Image.LANCZOS).save(out)
    return out


def urgent_cover(headline, footer="", action="", out="/app/outbox/_cover.png"):
    img = Image.new("RGB", (W * SS, H * SS), GRAPHITE)
    d = ImageDraw.Draw(img)
    pad = 80 * SS
    _frame(d, pad, AMBER, "Срочно")
    fh = _f("InterDisplay-SemiBold.ttf", 62)
    y = pad + 190 * SS
    for ln in _wrap(d, headline, fh, W * SS - pad * 2 - 20 * SS)[:3]:
        d.text((pad, y), ln, font=fh, fill=LIGHT)
        y += 84 * SS
    if action:
        y += 30 * SS
        d.line([(pad, y), (pad + 120 * SS, y)], fill=AMBER, width=3 * SS)
        y += 28 * SS
        fa = _f("Inter-Medium.ttf", 30)
        for ln in _wrap(d, action, fa, W * SS - pad * 2)[:3]:
            d.text((pad, y), ln, font=fa, fill=MUTED)
            y += 44 * SS
    _footer(d, pad, footer)
    return _save(img, out)


def digest_cover(period, items, out="/app/outbox/_digest.png"):
    img = Image.new("RGB", (W * SS, H * SS), GRAPHITE)
    d = ImageDraw.Draw(img)
    pad = 80 * SS
    _frame(d, pad, JADE, "Дайджест недели")
    d.text((pad, pad + 150 * SS), period,
           font=_f("InterDisplay-SemiBold.ttf", 56), fill=LIGHT)
    y = pad + 260 * SS
    ft = _f("Inter-Medium.ttf", 32)
    fs = _f("Inter-Regular.ttf", 27)
    for theme, gist in list(items)[:4]:
        ch = 108 * SS
        d.rectangle((pad, y, W * SS - pad, y + ch), fill=SLATE)
        d.rectangle((pad, y, pad + 5 * SS, y + ch), fill=JADE)
        d.text((pad + 28 * SS, y + 20 * SS), theme, font=ft, fill=LIGHT)
        g = _wrap(d, gist, fs, W * SS - pad * 2 - 56 * SS)
        if g:
            d.text((pad + 28 * SS, y + 62 * SS), g[0], font=fs, fill=MUTED)
        y += ch + 18 * SS
    _footer(d, pad, "Что вступает в силу на этой неделе")
    return _save(img, out)


def trois_cover(period, n_added, n_freed, out="/app/outbox/_trois.png"):
    img = Image.new("RGB", (W * SS, H * SS), GRAPHITE)
    d = ImageDraw.Draw(img)
    pad = 80 * SS
    _frame(d, pad, AMBER, "ТРОИС · Реестр")

    d.text((pad, pad + 160 * SS), "Реестр товарных знаков",
           font=_f("InterDisplay-SemiBold.ttf", 58), fill=LIGHT)
    if period:
        d.text((pad, pad + 245 * SS), period,
               font=_f("Inter-Regular.ttf", 30), fill=MUTED)

    y = pad + 330 * SS
    fn = _f("InterDisplay-SemiBold.ttf", 72)
    fl = _f("Inter-Regular.ttf", 26)
    for val, label, col in ((n_added, "новых знаков", AMBER),
                            (n_freed, "защита снята", JADE)):
        d.text((pad, y), str(val), font=fn, fill=col)
        d.text((pad + 110 * SS, y + 30 * SS), label, font=fl, fill=MUTED)
        y += 100 * SS

    _footer(d, pad, "Проверьте свою номенклатуру")
    return _save(img, out)
