#!/usr/bin/env python3
"""Отправляет посты из outbox/pending.json прямо в Telegram."""
import json, os, pathlib, sys, time
sys.path.insert(0, "/app")
from services.publisher.telegram_client import TelegramClient

PENDING = pathlib.Path("/app/outbox/pending.json")
SENT = pathlib.Path("/app/outbox/sent.json")

def main():
    if not PENDING.exists():
        print("очередь пуста"); return 0
    posts = json.loads(PENDING.read_text() or "[]")
    if not posts:
        print("очередь пуста"); return 0
    log = json.loads(SENT.read_text() or "[]") if SENT.exists() else []
    done = {e.get("item_id") for e in log}
    chat = os.environ.get("TELEGRAM_TARGET_CHAT") or os.environ["TELEGRAM_CHANNEL_ID"]
    tg = TelegramClient()
    left, n = [], 0
    for p in posts:
        if p.get("item_id") in done:
            continue
        try:
            mid = tg.send(chat, p["text"])
        except Exception as e:
            print("ошибка:", str(e)[:120]); left.append(p); continue
        print("отправлено #%s: %s" % (mid, p.get("title", "")[:60]))
        log.append({"item_id": p.get("item_id"), "title": p.get("title"),
python3 - <<'PY'
import pathlib, re
p = pathlib.Path("daily.sh")
s = p.read_text()
i = s.find('git add "$QUEUE"')
if i > 0:
    s = s[:i] + '''docker compose run --rm $MOUNT ingestion \\
    python tools/send_queue.py 2>&1 | tee -a "$LOG"
log "$MODE: готово"
'''
    p.write_text(s)
    print("применено")
else:
    print("не найдено")
