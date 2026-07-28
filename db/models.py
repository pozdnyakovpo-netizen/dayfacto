"""
SQLAlchemy 2.0 ORM-модели. MVP-подмножество таблиц из БЛОК 4:
raw_items, sources, stories, story_items — минимум, нужный для
сквозного пути ingestion → dedup → clustering (Phase 1).
Остальные таблицы (scores, drafts, decisions, publish_log,
analytics_snapshots, moderation_queue, monetization_*, system_config,
audit_log) добавляются в миграции Phase 2+ по мере написания
соответствующих сервисов — не создаём заранее то, что нечем наполнить.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SourceModel(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # "rss" | "telegram"
    url: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    reliability_score: Mapped[float] = mapped_column(Float, default=0.5)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    raw_items: Mapped[list["RawItemModel"]] = relationship(back_populates="source")


class RawItemModel(Base):
    __tablename__ = "raw_items"
    __table_args__ = (UniqueConstraint("raw_hash", name="uq_raw_items_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    raw_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="new")

    source: Mapped["SourceModel"] = relationship(back_populates="raw_items")
    story_links: Mapped[list["StoryItemModel"]] = relationship(back_populates="raw_item")


class StoryModel(Base):
    __tablename__ = "stories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_title: Mapped[str] = mapped_column(Text, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(16), default="open")  # "open" | "closed"
    embedding_id: Mapped[str | None] = mapped_column(String(128), nullable=True)  # Phase 3+ (Qdrant ref)
    related_story_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id"), nullable=True
    )

    items: Mapped[list["StoryItemModel"]] = relationship(back_populates="story")


class StoryItemModel(Base):
    __tablename__ = "story_items"

    story_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stories.id"), primary_key=True)
    raw_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("raw_items.id"), primary_key=True)
    similarity_score: Mapped[float] = mapped_column(Float, default=1.0)

    story: Mapped["StoryModel"] = relationship(back_populates="items")
    raw_item: Mapped["RawItemModel"] = relationship(back_populates="story_links")
