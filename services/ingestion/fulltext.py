import re
import html
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
STOP = ("Версия для печати", "Поделиться:", "Личный кабинет участника ВЭД")
NOISE = (
    "кибератак на информационные ресурсы",
    "Ваш браузер устарел",
    "Не удалось корректно загрузить страницу",
    "Вниманию участников информационного обмена",
    "обновить страницу или повторно зайти на сайт",
)


def _strip(h):
    h = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)
    h = re.sub(r"</p>|<br\s*/?>|</div>", "\n", h, flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", h))
    t = re.sub(r"[^\S\n]+", " ", t)
    return t


def fetch(url, timeout=25):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
        if r.status_code != 200:
            return None
        r.encoding = r.apparent_encoding or "utf-8"
        t = _strip(r.text)
    except Exception:
        return None
    for m in STOP:
        k = t.find(m)
        if k > 500:
            t = t[:k]
            break
    body = []
    for l in t.split("\n"):
        l = l.strip()
        if len(l) <= 90:
            continue
        if any(n in l for n in NOISE):
            continue
        body.append(l)
    out = "\n".join(body).strip()
    return out if len(out) > 200 else None
