"""
Точка входа сервиса ingestion. MVP-версия: простой polling-цикл по
активным источникам из таблицы sources, без очереди Redis (она
понадобится, когда появятся dedup/clustering-воркеры, которым нужно
СИГНАЛИЗИРОВАТЬ о новых raw_items, а не просто писать их в БД).
"""

import os
import time

from db.models import SourceModel
from db.session import get_session
from services.ingestion.rss import fetch_rss_source
from services.ingestion.telegram_scrape import fetch_telegram_source
from shared.logging import get_logger

os.environ.setdefault("SERVICE_NAME", "ingestion")
logger = get_logger(__name__)

POLL_INTERVAL_SECONDS = int(os.environ.get("INGESTION_POLL_INTERVAL", "300"))


def run_once() -> int:
    session = get_session()
    try:
        sources = session.query(SourceModel).filter(SourceModel.active.is_(True)).all()
    finally:
        session.close()

    if not sources:
        logger.warning("No active sources configured in the 'sources' table yet.")
        return 0

    total_new = 0
    for source in sources:
        if source.type == "rss":
            total_new += fetch_rss_source(source)
        elif source.type == "telegram":
            total_new += fetch_telegram_source(source)
        elif source.type == "html":
            from services.ingestion.html_list import fetch_html_source
            total_new += fetch_html_source(source)
        else:
            logger.warning(f"Unknown source type '{source.type}' for source={source.name}, skipping.")

    logger.info(f"Ingestion cycle complete: {total_new} new item(s) across {len(sources)} source(s).")
    return total_new


def main() -> None:
    logger.info(f"Ingestion service starting, poll interval = {POLL_INTERVAL_SECONDS}s")
    while True:
        try:
            run_once()
        except Exception as e:
            logger.error(f"Ingestion cycle failed: {e}", exc_info=True)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
