#!/usr/bin/env python3
"""Публикует посты из outbox/pending.json в Telegram.

Запускается в GitHub Actions, где Telegram доступен.
После успешной отправки очищает очередь и пишет журнал в outbox/sent.json.

Переменные окружения (в Actions - из секретов):
    TELEGRAM_BOT_TOKEN
    TELEGRAM_TARGET_CHAT   - куда слать (админ-чат или id канала)
"""

import json
import os
import pathlib
import time
import urllib.parse
import urllib.request

PENDING = pathlib.Path("outbox/pending.json")
SENT = pathlib.Path("outbox/sent.json")
API = "https://api.telegram.org/bot%s/%s"


MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря")


def _ru(iso):
    try:
        y, m, d = iso.split("-")
        return "Вступает в силу %d %s %s" % (int(d), MONTHS[int(m) - 1], y)
    except Exception:
        return ""


def _send_img(token, chat, text, img):
    import uuid, urllib.request
    b = uuid.uuid4().hex
    parts = []
    for k, v in (("chat_id", chat), ("caption", text), ("parse_mode", "HTML")):
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                      % (b, k, v)).encode())
    parts.append(("--%s\r\nContent-Disposition: form-data; name=\"photo\"; "
                  "filename=\"c.png\"\r\nContent-Type: image/png\r\n\r\n" % b).encode())
    parts.append(open(img, "rb").read())
    parts.append(("\r\n--%s--\r\n" % b).encode())
    req = urllib.request.Request(API % (token, "sendPhoto"), data=b"".join(parts))
    req.add_header("Content-Type", "multipart/form-data; boundary=%s" % b)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
        return d["result"]["message_id"] if d.get("ok") else None
    except Exception as exc:
        print("  (sendPhoto не прошёл: %s)" % str(exc)[:80])
        return None


def send_photo(token, chat, text, post):
    """Пост с обложкой. Возвращает message_id или None."""
    import re, uuid, urllib.request
    if len(text) > 1000:
        return None
    try:
        from services.editorial.cover import make, urgent_cover
        head = re.sub(r"<[^>]+>", "", (post.get("title") or "")).strip()
        head = re.sub(r"^Напоминание d\d+:\s*", "", head)
        if str(post.get("item_id", "")).endswith(("-d1", "-d7", "-d30")):
            img = urgent_cover(head[:150],
                               footer=_ru(post.get("effective_date") or ""),
                               action=(post.get("doc_number") or "")[:120],
                               out="/app/outbox/_cover.png")
            return _send_img(token, chat, text, img)
        img = make(head[:160],
                   change_type=post.get("change_type", ""),
                   effective_date=_ru(post.get("effective_date") or ""),
                   note=(post.get("doc_number") or "")[:110],
                   urgent=str(post.get("item_id", "")).endswith(("-d1", "-d7")),
                   out="/app/outbox/_cover.png")
    except Exception as exc:
        print("  (обложка не собрана: %s)" % str(exc)[:80])
        return None
    return _send_img(token, chat, text, img)



def send(token: str, chat: str, text: str) -> int:
    data = urllib.parse.urlencode({
        "chat_id": chat,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    url = API % (token, "sendMessage")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, data=data, timeout=30) as r:
                payload = json.loads(r.read().decode())
            if payload.get("ok"):
                return payload["result"]["message_id"]
            raise RuntimeError(payload.get("description", "неизвестная ошибка"))
        except Exception as exc:
            if attempt == 2:
                raise
            wait = 3 * (attempt + 1)
            print("  повтор через %ds: %s" % (wait, exc))
            time.sleep(wait)
    return 0


def _doc_published(post):
    import os
    from sqlalchemy import create_engine, text as _t
    doc = (post.get("doc_number") or "").strip()
    url = os.environ.get("DATABASE_URL")
    if len(doc) < 8 or not url:
        return None
    try:
        with create_engine(url).connect() as c:
            r = c.execute(_t("SELECT doc_number FROM published_stories "
                             "WHERE doc_number = :d LIMIT 1"), {"d": doc}).first()
        return r[0] if r else None
    except Exception:
        return None


def _mark_sent(post, mid, chat):
    import os
    from sqlalchemy import create_engine, text as _t
    url = os.environ.get("DATABASE_URL")
    if not url:
        return
    iid = str(post.get("item_id") or "")
    try:
        db = create_engine(url)
        with db.begin() as c:
            base, _, kind = iid.rpartition("-")
            if kind in ("d1", "d7", "d30") and base:
                c.execute(_t("INSERT INTO ved_reminders_sent (raw_item_id, kind) "
                             "VALUES (CAST(:i AS uuid), :k) ON CONFLICT DO NOTHING"),
                          {"i": base, "k": kind})
            else:
                c.execute(_t("INSERT INTO published_stories "
                             "(story_id, message_id, chat_id, headline, doc_number) "
                             "VALUES (CAST(:i AS uuid), :m, :c, :h, :d) "
                             "ON CONFLICT DO NOTHING"),
                          {"i": iid, "m": mid, "c": str(chat),
                           "h": (post.get("title") or "")[:300],
                           "d": (post.get("doc_number") or "")[:500]})
    except Exception as exc:
        print("  (журнал в БД не записан: %s)" % str(exc)[:90])


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_TARGET_CHAT", "")
    if not token or not chat:
        print("нет TELEGRAM_BOT_TOKEN или TELEGRAM_TARGET_CHAT")
        return 1

    if not PENDING.exists():
        print("очередь пуста")
        return 0

    posts = json.loads(PENDING.read_text() or "[]")
    if not posts:
        print("очередь пуста")
        return 0

    log = []
    if SENT.exists():
        try:
            log = json.loads(SENT.read_text() or "[]")
        except json.JSONDecodeError:
            log = []
    already = {e.get("item_id") for e in log}

    failed = []
    for post in posts:
        if post.get("item_id") in already:
            print("уже отправлено: %s" % post.get("title", "")[:50])
            continue
        _dup = _doc_published(post)
        if _dup:
            print("пропуск, документ уже освещался: %s" % _dup[:60])
            continue
        try:
            mid = send(token, chat, post["text"])
        except Exception as exc:
            print("ОШИБКА: %s -> %s" % (post.get("title", "")[:50], exc))
            failed.append(post)
            continue
        print("отправлено #%s: %s" % (mid, post.get("title", "")[:50]))
        _mark_sent(post, mid, chat)
        log.append({
            "item_id": post.get("item_id"),
            "title": post.get("title"),
            "message_id": mid,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        time.sleep(3)

    SENT.parent.mkdir(parents=True, exist_ok=True)
    SENT.write_text(json.dumps(log[-500:], ensure_ascii=False, indent=2),
                    encoding="utf-8")
    PENDING.write_text(json.dumps(failed, ensure_ascii=False, indent=2),
                       encoding="utf-8")

    print("\nитого отправлено: %d, осталось в очереди: %d"
          % (len(log) - len(already), len(failed)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
