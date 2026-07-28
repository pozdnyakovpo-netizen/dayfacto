"""
Общие data contracts (pydantic-модели), на которые опираются ВСЕ сервисы.
Это первый файл, который нужно написать (см. БЛОК 14, шаг 1) — изменение
полей здесь затрагивает весь пайплайн, поэтому модели держим строгими
(pydantic валидирует на границе между сервисами и очередями Redis).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class SourceType(str, Enum):
    RSS = "rss"
    TELEGRAM = "telegram"


class RawItemStatus(str, Enum):
    NEW = "new"
    DEDUPED = "deduped"          # признан дублем, дальше не идёт
    CLUSTERED = "clustered"       # вошёл в story
    DISCARDED = "discarded"       # отброшен фильтром (не новость/реклама и т.п.)


class RawItem(BaseModel):
    """Один элемент, полученный от источника ДО дедупа/кластеризации."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    source_id: uuid.UUID
    source_type: SourceType
    url: Optional[str] = None
    title: str
    body: str = ""
    published_at: Optional[datetime] = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    raw_hash: str  # sha256 от нормализованного (url или title+source)
    status: RawItemStatus = RawItemStatus.NEW


class Source(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    type: SourceType
    url: str
    weight: float = 1.0
    reliability_score: float = 0.5
    active: bool = True


class StoryStatus(str, Enum):
    OPEN = "open"      # ещё может получать новые raw_item (развивающееся событие)
    CLOSED = "closed"


class Story(BaseModel):
    """Кластер из одного или нескольких RawItem, описывающих одно событие."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    canonical_title: str
    first_seen_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated_at: datetime = Field(default_factory=datetime.utcnow)
    status: StoryStatus = StoryStatus.OPEN
    embedding_id: Optional[str] = None  # ссылка на вектор в Qdrant (Phase 3+)
    related_story_id: Optional[uuid.UUID] = None  # "продолжение истории"


class Scores(BaseModel):
    """См. БЛОК 6 — все под-score в диапазоне [0.0, 1.0]."""

    story_id: uuid.UUID
    relevance: float = Field(ge=0.0, le=1.0)
    novelty: float = Field(ge=0.0, le=1.0)
    dup_risk: float = Field(ge=0.0, le=1.0)
    style: float = Field(ge=0.0, le=1.0, default=0.0)
    readability: float = Field(ge=0.0, le=1.0, default=0.0)
    trust: float = Field(ge=0.0, le=1.0)
    sensationalism_risk: float = Field(ge=0.0, le=1.0, default=0.0)
    monetization_potential: float = Field(ge=0.0, le=1.0, default=0.0)
    fatigue: float = Field(ge=0.0, le=1.0, default=0.0)
    audience_fit: float = Field(ge=0.0, le=1.0, default=1.0)
    final_score: Optional[float] = None
    computed_at: datetime = Field(default_factory=datetime.utcnow)


class Draft(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    story_id: uuid.UUID
    version: int = 1
    headline: str
    body: str
    why_it_matters: Optional[str] = None
    template_used: str = "short_post"
    llm_provider: str
    tokens_used: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DecisionType(str, Enum):
    PUBLISH = "publish"
    REWRITE = "rewrite"
    HOLD = "hold"
    MODERATE = "moderate"
    DROP = "drop"


class DecisionResult(BaseModel):
    story_id: uuid.UUID
    draft_id: Optional[uuid.UUID] = None
    decision: DecisionType
    decided_by: str = "engine"  # "engine" | admin username
    reason: str = ""
    decided_at: datetime = Field(default_factory=datetime.utcnow)
