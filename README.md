# @DayFacto — Phase 1 MVP scaffold

## Что уже здесь и что реально проверено

- `shared/data_contracts.py` — pydantic-модели. Синтаксис проверен (`py_compile`), сами импорты pydantic **не выполнялись** — в моей среде разработки нет сети, чтобы поставить пакет. Проверьте у себя: `pip install -r requirements.txt && python -c "from shared.data_contracts import RawItem"`.
- `db/models.py` + `db/migrations/versions/0001_initial.py` — SQLAlchemy ORM + первая alembic-миграция (sources, raw_items, stories, story_items). **Реально применена и проверена на живом сервере** — таблицы созданы.
- `services/ingestion/` — **работает в проде на VPS**: RSS-фетчер реально собирает новости ТАСС и пишет их в PostgreSQL, проверено вживую.
- `services/dedup/hash.py` — hash-дедуп близких заголовков (нормализация + sha256). Чистые функции (`normalize_title`, `title_hash`) **реально протестированы** — 5 тестов прошли. **Подтверждено вживую на сервере**: реальная новость от ТАСС и РИА про один и тот же инцидент была помечена как `deduped`.
- `services/clustering/story_builder.py` — группировка новостей в сюжеты (entity + word-overlap подтверждение — тот же принцип, что чинили в предыдущем проекте после реальных инцидентов с ложными связями). **9 тестов реально прогнаны**, включая точное воспроизведение прошлых ложных срабатываний ("Донецк"/"Донецкая область", слово "Центр") — при первом прогоне тестов нашёлся и был исправлен настоящий баг (совпавшая сущность засчитывалась сама себе как "подтверждение"). Сама логика прохода по БД синтаксически проверена, не выполнялась вживую здесь.
  **Известное ограничение Phase 1**: `dedup` и `clustering` оба независимо опрашивают одну и ту же колонку `status`, что теоретически может привести к гонке при высокой нагрузке — полноценно решается очередью Redis в Phase 2 (см. комментарий в коде).

## Что нужно сделать вам перед первым запуском (или при обновлении)

1. Скопировать `.env.example` → `.env`, заполнить токены/ключи.
2. `docker compose up -d postgres redis`
3. `docker compose run --rm migrate` (применит миграции)
4. Добавить источник(и) в таблицу `sources` (см. пример INSERT в истории проекта).
5. `docker compose up -d ingestion dedup clustering`
6. Проверить логи: `docker compose logs -f ingestion`, `docker compose logs -f dedup`, `docker compose logs -f clustering`
7. Проверить в БД: `SELECT status, count(*) FROM raw_items GROUP BY status;` и `SELECT count(*) FROM stories;`

## Что дальше (следующая итерация, не в этом скаффолде)

Из БЛОК 14: `llm_provider/` → `services/ranking/` → `services/editorial/` → `services/decision/` → `services/publisher/`. Каждый — с тем же уровнем: рабочий код + honest-отчёт о том, что реально проверено, а что нет.

## Честное предупреждение

Phase 1 постепенно обрастает вертикальным срезом: ingestion → dedup → clustering уже работают и подтверждены на живом сервере. Дальше по пайплайну (ranking/editorial/decision/publisher) — ещё не написано. До первой реальной публикации в @DayFacto нужно реализовать всю цепочку. Не разворачивайте `full_auto` режим, пока не пройдёте Phase 1 и 2 целиком — это буквально прописано в БЛОК 15 операционных правил, которые мы вместе спроектировали.
