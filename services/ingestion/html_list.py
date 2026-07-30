"""Сбор новостей с сайтов без RSS (ЕЭК и подобные)."""
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from sqlalchemy.exc import IntegrityError

from db.models import RawItemModel
from db.session import get_session
from shared.logging import get_logger

logger = get_logger("ingestion.html")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
DATE_RE = re.compile(r"^(\d{1,2})\s+([а-яё]+)\s+(\d{4})\s+(.+)$", re.I)
MONTHS = {m: i + 1 for i, m in enumerate(
    ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
     "августа", "сентября", "октября", "ноября", "декабря"])}


def _hash(link):
    return hashlib.sha256(link.encode("utf-8")).hexdigest()


def fetch_html_source(source, limit: int = 20) -> int:
    try:
        r = requests.get(source.url, headers=UA, timeout=30)
        r.raise_for_status()
    except Exception as e:
        logger.warning("HTML source=%s недоступен: %s" % (source.name, e))
        return 0

    soup = BeautifulSoup(r.text, "html.parser")
    seen, items = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/news/" not in href or href.rstrip("/").endswith("/news"):
            continue
        txt = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        m = DATE_RE.match(txt)
        if not m:
            continue
        title = m.group(4).strip()
        if len(title) < 25:
            continue
        link = urljoin(source.url, href)
        if link in seen:
            continue
        seen.add(link)
        try:
            pub = datetime(int(m.group(3)), MONTHS[m.group(2).lower()],
                           int(m.group(1)), tzinfo=timezone.utc)
        except Exception:
            pub = None
        items.append((link, title, pub))
        if len(items) >= limit:
            break
    return _store(source, items)


def _store(source, items) -> int:
    from services.ingestion.fulltext import fetch as fetch_full
    session = get_session()
    inserted = 0
    try:
        for link, title, pub in items:
            h = _hash(link)
            if session.query(RawItemModel.id).filter_by(raw_hash=h).first():
                continue
            body = fetch_full(link) or title
            item = RawItemModel(
                source_id=source.id, source_type="html", url=link,
                title=title[:2000], body=body[:8000], published_at=pub,
                fetched_at=datetime.now(timezone.utc),
                raw_hash=h, status="new")
            session.add(item)
            try:
                session.commit()
                inserted += 1
            except IntegrityError:
                session.rollback()
    finally:
        session.close()
    logger.info("HTML source=%s: %d new item(s) inserted." % (source.name, inserted))
    return inserted
