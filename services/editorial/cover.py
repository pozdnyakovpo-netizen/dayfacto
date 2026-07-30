import os
import re
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
SS = 2

GRAPHITE = (15, 19, 24)
EMERALD = (31, 122, 90)
LIGHT = (243, 245, 244)
MUTED = (167, 178, 173)
LINE = (39, 48, 56)
AMBER = (200, 146, 46)

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
    d.rectangle((pad, pad, pad + 6 * SS, pad + 84 * SS), fill=accent)

    badge = "Срок" if urgent else BADGE.get(change_type, "Изменение")
    d.text((pad + 30 * SS, pad + 22 * SS), badge.upper(),
           font=_f("Inter-SemiBold.ttf", 22), fill=accent)

    fh = _f("InterDisplay-SemiBold.ttf", 54)
    y = pad + 130 * SS
    for ln in _wrap(d, headline, fh, W * SS - pad * 2 - 20 * SS)[:3]:
        d.text((pad, y), ln, font=fh, fill=LIGHT)
        y += 72 * SS

    if note:
        fn = _f("Inter-Regular.ttf", 26)
        y += 14 * SS
        for ln in _wrap(d, note, fn, W * SS - pad * 2)[:2]:
            d.text((pad, y), ln, font=fn, fill=MUTED)
            y += 38 * SS

    ly = H * SS - pad - 76 * SS
    d.line([(pad, ly), (W * SS - pad, ly)], fill=LINE, width=2 * SS)
    d.text((pad, ly + 26 * SS), effective_date or "",
           font=_f("Inter-Medium.ttf", 28), fill=LIGHT)

    fs = _f("Inter-Regular.ttf", 24)
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
