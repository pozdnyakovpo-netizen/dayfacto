"""
RSS-фетчер: реальная реализация на feedparser. Пишет новые записи в
raw_items с дедупом на уровне БД (unique constraint на raw_hash) —
если тот же raw_hash уже есть, INSERT просто не пройдёт, и это ловится
как штатный случай, а не ошибка (см. except IntegrityError ниже).
"""

import hashlib
import html
import re
from datetime import datetime, timezone

import feedparser
from sqlalchemy.exc import IntegrityError

from db.models import RawItemModel, SourceModel
from db.session import get_session
from shared.logging import get_logger
from shared.retry import retry_with_backoff

logger = get_logger(__name__)


def _raw_hash(source_id, url: str | None, title: str) -> str:
    basis = url or f"{source_id}:{title}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


@retry_with_backoff(max_attempts=3, exceptions=(Exception,))
def _fetch_feed(url: str):
    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        # bozo=True значит "фид не совсем валиден", но entries иногда
        # всё равно парсятся — падаем только если entries пустой.
        raise RuntimeError(f"Failed to parse feed {url}: {parsed.bozo_exception}")
    return parsed.entries


def fetch_rss_source(source: SourceModel, limit: int = 30) -> int:
    """Возвращает количество НОВЫХ (реально вставленных) записей."""
    try:
        entries = _fetch_feed(source.url)
    except Exception as e:
        logger.warning(f"RSS fetch failed for source={source.name} url={source.url}: {e}")
        return 0

    session = get_session()
    inserted = 0
    try:
        for entry in entries[:limit]:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", None)
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            _full = getattr(entry, "text", "") or ""
            if len(_full) > len(summary):
                summary = _full
            summary = ' '.join(re.sub('<[^>]+>', ' ', html.unescape(summary or '')).split())
            if not title:
                continue

            published_at = None
            if getattr(entry, "published_parsed", None):
                published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

            item = RawItemModel(
                source_id=source.id,
                source_type="rss",
                url=link,
                title=title[:2000],
                body=summary[:8000],
                published_at=published_at,
                fetched_at=datetime.now(timezone.utc),
                raw_hash=_raw_hash(source.id, link, title),
                status="new",
            )
            session.add(item)
            try:
                session.commit()
                inserted += 1
            except IntegrityError:
                # Дубль по raw_hash — штатная ситуация, не ошибка.
                session.rollback()
    finally:
        session.close()

    logger.info(f"RSS source={source.name}: {inserted} new item(s) inserted.")
    return inserted
