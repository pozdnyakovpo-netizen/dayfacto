# @DayFacto — Phase 1 MVP scaffold

## Что уже здесь и что реально проверено

- `shared/data_contracts.py` — pydantic-модели. Синтаксис проверен (`py_compile`), сами импорты pydantic **не выполнялись** — в моей среде разработки нет сети, чтобы поставить пакет. Проверьте у себя: `pip install -r requirements.txt && python -c "from shared.data_contracts import RawItem"`.
- `db/models.py` + `db/migrations/versions/0001_initial.py` — SQLAlchemy ORM + первая alembic-миграция (sources, raw_items, stories, story_items). Синтаксис проверен, реальный `alembic upgrade head` против Postgres — не выполнялся (нет доступа к серверу БД отсюда).
- `services/ingestion/normalizer.py` — **реально протестирован**, 5 unit-тестов прошли (`tests/unit/test_normalizer.py`).
- `services/ingestion/rss.py`, `telegram_scrape.py`, `main.py` — синтаксис проверен, логика адаптирована из уже работающего в проде подхода (@deepdailyfact), но сетевые вызовы здесь не выполнялись.

## Что нужно сделать вам перед первым запуском

1. Скопировать `.env.example` → `.env`, заполнить токены/ключи.
2. `docker compose up -d postgres redis`
3. `docker compose run --rm migrate` (применит миграцию 0001)
4. Вручную добавить хотя бы один источник в таблицу `sources` (пока нет admin-api/seed-скрипта — сделать через `psql` или Python-скрипт):
   ```sql
   INSERT INTO sources (id, name, type, url, weight, reliability_score, active)
   VALUES (gen_random_uuid(), 'ТАСС RSS', 'rss', 'https://tass.ru/rss/v2.xml', 1.0, 0.9, true);
   ```
5. `docker compose up -d ingestion`
6. Проверить: `docker compose logs -f ingestion` — должны появиться записи `"N new item(s) inserted"`.
7. Проверить в БД: `SELECT count(*) FROM raw_items;`

## Что дальше (следующая итерация, не в этом скаффолде)

Из БЛОК 14: `services/dedup/hash.py` → `services/clustering/story_builder.py` → `llm_provider/` → `services/ranking/` → `services/editorial/` → `services/decision/` → `services/publisher/`. Каждый — с тем же уровнем: рабочий код + honest-отчёт о том, что реально проверено, а что нет.

## Честное предупреждение

Это Phase 1, самый первый вертикальный срез. Ingestion уже может писать в БД, но дальше по пайплайну (dedup/cluster/ranking/editorial/decision/publisher) — ещё не написано. До первой реальной публикации в @DayFacto нужно реализовать всю цепочку из docker-compose.yml (сейчас закомментирована). Не разворачивайте `full_auto` режим, пока не пройдёте Phase 1 и 2 целиком — это буквально прописано в БЛОК 15 операционных правил, которые мы вместе спроектировали.
