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


def send(token: str, chat: str, text: str) -> int:
    data = urllib.parse.urlencode({
        "chat_id": chat,
        "text": text,
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
        try:
            mid = send(token, chat, post["text"])
        except Exception as exc:
            print("ОШИБКА: %s -> %s" % (post.get("title", "")[:50], exc))
            failed.append(post)
            continue
        print("отправлено #%s: %s" % (mid, post.get("title", "")[:50]))
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
