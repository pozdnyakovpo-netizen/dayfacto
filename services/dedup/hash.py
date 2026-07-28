"""
БЛОК 14, шаг 4 — hash-дедуп (Phase 1, до появления embedding-дедупа
на Qdrant в Phase 3). Задача этого модуля: находить новости, которые
РАЗНЫЕ источники опубликовали про одно и то же (разный url/raw_hash,
но по сути один и тот же текст) — до кластеризации по сюжетам.

Точный дубль по ссылке уже отсекается на уровне БД (unique constraint
на raw_hash в rss.py/telegram_scrape.py) — этот модуль ловит СЛЕДУЮЩИЙ
уровень: близкие по формулировке заголовки из разных источников.
"""

import hashlib
import re
from datetime import datetime, timedelta, timezone

from db.models import RawItemModel
from db.session import get_session
from shared.logging import get_logger

logger = get_logger(__name__)

LOOKBACK_HOURS = 48


def normalize_title(title: str) -> str:
    """Приводит заголовок к canonical-виду для сравнения:
    нижний регистр, только буквы/цифры/пробелы, схлопнутые пробелы.
    Специально грубая нормализация — тонкая семантическая близость
    (перефразированные, но неточные совпадения) остаётся за
    embedding-дедупом в Phase 3, здесь — только явные близкие дубли.
    """
    if not title:
        return ""
    t = title.lower()
    t = re.sub(r"[^a-zа-яё0-9\s]", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def title_hash(title: str) -> str:
    normalized = normalize_title(title)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def run_dedup_pass(lookback_hours: int = LOOKBACK_HOURS) -> int:
    """Возвращает количество элементов, помеченных как дубли за этот проход."""
    session = get_session()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

        # "Уже виденные" канонические хеши — из ЛЮБых статусов за окно
        # lookback (не только new): так дубль ловится и против уже
        # кластеризованных/ранее помеченных дублями новостей, а не
        # только внутри текущей необработанной пачки.
        reference_items = (
            session.query(RawItemModel)
            .filter(RawItemModel.fetched_at >= cutoff)
            .filter(RawItemModel.status != "new")
            .all()
        )
        seen_hashes = {title_hash(item.title) for item in reference_items}

        candidates = (
            session.query(RawItemModel)
            .filter(RawItemModel.status == "new")
            .filter(RawItemModel.fetched_at >= cutoff)
            .order_by(RawItemModel.fetched_at.asc())
            .all()
        )

        marked_dup = 0
        for item in candidates:
            h = title_hash(item.title)
            if h in seen_hashes:
                item.status = "deduped"
                marked_dup += 1
            else:
                seen_hashes.add(h)
                # Остаётся status="new" — сигнал для clustering-service,
                # что этот элемент готов к группировке в сюжет.

        session.commit()
    finally:
        session.close()

    logger.info(f"Dedup pass complete: {marked_dup} item(s) marked as duplicates.")
    return marked_dup
