"""
Скрейпер публичной preview-страницы Telegram-канала (t.me/s/<username>) —
без Bot API, без токена, тот же проверенный подход, что уже надёжно
работает в существующем боте @deepdailyfact. Пишет в raw_items так же,
как rss.py — дедуп по raw_hash на уровне БД.
"""

import hashlib
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from sqlalchemy.exc import IntegrityError

from db.models import RawItemModel, SourceModel
from db.session import get_session
from shared.logging import get_logger
from shared.retry import retry_with_backoff

logger = get_logger(__name__)

PREVIEW_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


def _raw_hash(link: str) -> str:
    return hashlib.sha256(link.encode("utf-8")).hexdigest()


@retry_with_backoff(max_attempts=3, exceptions=(requests.RequestException,))
def _fetch_page(username: str) -> str:
    resp = requests.get(f"https://t.me/s/{username}", headers=PREVIEW_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


CAL_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})\s+вступают?\s+в\s+силу")


def split_calendar(title, body):
    """Календарь Альты -> список (заголовок, текст) по одному изменению."""
    m = CAL_RE.search(title + " " + body[:120])
    if not m or "\u2705" not in body:
        return None
    day, mon, year = m.groups()
    tail = body.split("\u2705", 1)[1]
    tail = re.split(r"\U0001F4C5|Весь таможенный календарь", tail)[0]
    out = []
    for chunk in ("\u2705" + tail).split("\u2705"):
        c = re.sub(r"\s+", " ", chunk).strip(" .")
        if len(c) < 30:
            continue
        head = c[:110].rsplit(" ", 1)[0] if len(c) > 110 else c
        txt = "С %s.%s.%s вступает в силу: %s" % (day, mon, year, c)
        out.append((head, txt))
    return out or None


def fetch_telegram_source(source: SourceModel, limit: int = 20) -> int:
    username = source.url.rstrip("/").split("/")[-1].lstrip("@")
    try:
        html_text = _fetch_page(username)
    except Exception as e:
        logger.warning(f"Telegram scrape failed for @{username}: {e}")
        return 0

    soup = BeautifulSoup(html_text, "html.parser")
    messages = soup.select("div.tgme_widget_message")[-limit:]

    session = get_session()
    inserted = 0
    try:
        for msg in messages:
            post_id = msg.get("data-post")
            if not post_id:
                continue
            link = f"https://t.me/{post_id}"

            text_el = msg.select_one(".tgme_widget_message_text")
            raw_text = text_el.get_text("\n", strip=True) if text_el else ""
            if not raw_text:
                continue

            _lines = [l.strip() for l in raw_text.split("\n")]
            _good = [l for l in _lines
                     if len(re.sub(r"[^\w\s]", "", l).strip()) >= 15]
            title = (_good[0] if _good else re.sub(r"\s+", " ", raw_text).strip())[:2000]
            body = re.sub(r"\s+", " ", raw_text).strip()[:8000]

            time_el = msg.select_one("time")
            published_at = None
            if time_el and time_el.get("datetime"):
                try:
                    published_at = datetime.fromisoformat(time_el["datetime"])
                except ValueError:
                    published_at = None

            _parts = split_calendar(title, body)
            if _parts:
                for _n, (_h, _t) in enumerate(_parts, 1):
                    _it = RawItemModel(
                        source_id=source.id, source_type="telegram",
                        url=link, title=_h[:2000], body=_t[:8000],
                        published_at=published_at,
                        fetched_at=datetime.now(timezone.utc),
                        raw_hash=_raw_hash("%s#%d" % (link, _n)),
                        status="new")
                    session.add(_it)
                    try:
                        session.commit()
                        inserted += 1
                    except IntegrityError:
                        session.rollback()
                continue

            item = RawItemModel(
                source_id=source.id,
                source_type="telegram",
                url=link,
                title=title,
                body=body,
                published_at=published_at,
                fetched_at=datetime.now(timezone.utc),
                raw_hash=_raw_hash(link),
                status="new",
            )
            session.add(item)
            try:
                session.commit()
                inserted += 1
            except IntegrityError:
                session.rollback()
    finally:
        session.close()

    logger.info(f"Telegram source=@{username}: {inserted} new item(s) inserted.")
    return inserted
