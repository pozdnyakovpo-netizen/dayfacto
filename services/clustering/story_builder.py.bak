"""
БЛОК 14, шаг 5 — базовая кластеризация (без Qdrant, который появится
в Phase 3). Группирует raw_items с одинаковым событием в единый Story.

ВАЖНЫЙ УРОК из предыдущего проекта (бот @deepdailyfact): связывать
новости ТОЛЬКО по одному совпавшему именному стему (обрубку слова)
недостаточно — "Донецк" и "Донецкая область", "владимир" (имя) и
"Владимир" (город) дают одинаковый стем, но это разные сущности.
Реальный инцидент: слово "Центр" (название группировки войск) ложно
связывало вообще любые не относящиеся друг к другу новости, потому что
это ещё и обычное слово ("торговый центр" и т.п.). Поэтому здесь
СОВПАДЕНИЕ СУЩНОСТИ — необходимое, но НЕ достаточное условие: всегда
требуется ЕЩЁ и реальное пересечение слов темы (не только сущностей).
"""

import re
from datetime import datetime, timedelta, timezone

from db.models import RawItemModel, StoryItemModel, StoryModel
from db.session import get_session
from shared.logging import get_logger

logger = get_logger(__name__)

CLUSTER_LOOKBACK_HOURS = 48
WORD_OVERLAP_THRESHOLD = 0.15

STOPWORDS = {
    "и", "в", "на", "с", "со", "по", "за", "для", "от", "к", "из", "у", "о", "об",
    "при", "до", "под", "над", "же", "ли", "бы", "не", "но", "а", "то", "там", "тут",
    "эта", "этот", "эти", "это", "как", "их", "его", "её", "стал", "стала", "стали",
    "новый", "новая", "новые", "после", "более", "менее", "который", "которая",
}

# ФИКС (реальный инцидент из предыдущего проекта): слова, которые внешне
# выглядят как именные сущности (с большой буквы), но на практике —
# обычные частотные слова или используются и как обычные слова тоже
# ("Центр" — и название группировки войск, и просто "торговый центр").
COMMON_ENTITY_STOPWORDS = {
    "росси", "москв", "украи", "путин", "кремл", "центр", "запад", "восток", "север",
}


def significant_words(text: str) -> set[str]:
    if not text:
        return set()
    t = text.lower()
    t = re.sub(r"[^a-zа-яё0-9\s]", " ", t, flags=re.IGNORECASE)
    words = set()
    for w in t.split():
        if len(w) <= 2 or w in STOPWORDS:
            continue
        stem = w[:6] if len(w) > 6 else w
        words.add(stem)
    return words


def extract_entity_stems(text: str) -> set[str]:
    if not text:
        return set()
    words = re.findall(r"[А-ЯЁ][а-яё]+", text)
    stems = set()
    for w in words:
        wl = w.lower()
        if len(wl) <= 3 or wl in STOPWORDS:
            continue
        stem = wl[:6] if len(wl) > 6 else wl
        if stem in COMMON_ENTITY_STOPWORDS:
            continue
        stems.add(stem)
    return stems


def titles_are_similar(words_a: set[str], words_b: set[str], threshold: float = 0.5) -> bool:
    if not words_a or not words_b:
        return False
    smaller = min(len(words_a), len(words_b))
    if smaller == 0:
        return False
    return (len(words_a & words_b) / smaller) >= threshold


def is_same_event(text_a: str, text_b: str) -> bool:
    words_a = significant_words(text_a)
    words_b = significant_words(text_b)
    if titles_are_similar(words_a, words_b, threshold=0.5):
        return True
    entities_a = extract_entity_stems(text_a)
    entities_b = extract_entity_stems(text_b)
    shared_entities = entities_a & entities_b
    if shared_entities:
        # ФИКС (найдено реальным запуском тестов): совпавшие сущности —
        # это ЧАСТЬ множества "значимых слов", поэтому без исключения их
        # отсюда подтверждение "самоподтверждается" тем же самым словом,
        # которое и создало совпадение (пример: "Донецк"/"Донецкая" дают
        # общий стем "донецк" — и как сущность, и как обычное слово, из-за
        # чего пересечение слов темы всегда содержит хотя бы это слово).
        # Исключаем совпавшие сущности из проверки пересечения СЛОВ —
        # нужно независимое подтверждение, а не то же самое совпадение
        # дважды.
        words_a_excl = words_a - shared_entities
        words_b_excl = words_b - shared_entities
        if titles_are_similar(words_a_excl, words_b_excl, threshold=WORD_OVERLAP_THRESHOLD):
            return True
    return False


def run_clustering_pass(lookback_hours: int = CLUSTER_LOOKBACK_HOURS) -> dict:
    # ЧЕСТНОЕ ОГРАНИЧЕНИЕ Phase 1: dedup-service и clustering-service оба
    # независимо опрашивают raw_items со status="new" на разных таймерах
    # (2 мин и 2.5 мин). Теоретически возможна гонка — один и тот же
    # элемент может быть обработан обоими сервисами почти одновременно
    # до того, как статус успеет обновиться. На объёме MVP (единицы
    # источников, интервалы разнесены) вероятность мала, но правильное
    # решение — очередь заданий (Redis), которая появится в Phase 2,
    # когда ingestion будет СИГНАЛИЗИРОВАТЬ остальным сервисам о новых
    # элементах, а не все будут по отдельности опрашивать одну и ту же
    # колонку status.
    session = get_session()
    stats = {"attached_to_existing": 0, "new_stories": 0}
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

        open_stories = (
            session.query(StoryModel)
            .filter(StoryModel.status == "open")
            .filter(StoryModel.last_updated_at >= cutoff)
            .all()
        )

        # Предзагружаем объединённый текст (все заголовки постов) для
        # каждого открытого сюжета — используется для сравнения.
        story_texts: dict = {}
        for story in open_stories:
            titles = (
                session.query(RawItemModel.title)
                .join(StoryItemModel, StoryItemModel.raw_item_id == RawItemModel.id)
                .filter(StoryItemModel.story_id == story.id)
                .all()
            )
            story_texts[story.id] = " ".join(t[0] for t in titles) or story.canonical_title

        candidates = (
            session.query(RawItemModel)
            .filter(RawItemModel.status == "new")
            .order_by(RawItemModel.fetched_at.asc())
            .all()
        )

        for item in candidates:
            matched_story = None
            for story in open_stories:
                if is_same_event(item.title, story_texts[story.id]):
                    matched_story = story
                    break

            if matched_story:
                session.add(StoryItemModel(story_id=matched_story.id, raw_item_id=item.id, similarity_score=0.8))
                matched_story.last_updated_at = datetime.now(timezone.utc)
                story_texts[matched_story.id] += " " + item.title
                item.status = "clustered"
                stats["attached_to_existing"] += 1
            else:
                new_story = StoryModel(
                    canonical_title=item.title,
                    first_seen_at=datetime.now(timezone.utc),
                    last_updated_at=datetime.now(timezone.utc),
                    status="open",
                )
                session.add(new_story)
                session.flush()  # получить new_story.id до commit
                session.add(StoryItemModel(story_id=new_story.id, raw_item_id=item.id, similarity_score=1.0))
                item.status = "clustered"
                open_stories.append(new_story)
                story_texts[new_story.id] = item.title
                stats["new_stories"] += 1

            session.commit()
    finally:
        session.close()

    logger.info(
        f"Clustering pass complete: {stats['new_stories']} new story(ies), "
        f"{stats['attached_to_existing']} item(s) attached to existing stories."
    )
    return stats
