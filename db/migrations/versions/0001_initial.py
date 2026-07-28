"""initial MVP tables

Revision ID: 0001
Revises:
Create Date: 2026-07-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("weight", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("reliability_score", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "stories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canonical_title", sa.Text, nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("embedding_id", sa.String(128), nullable=True),
        sa.Column(
            "related_story_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stories.id"),
            nullable=True,
        ),
    )

    op.create_table(
        "raw_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False, server_default=""),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="new"),
    )
    op.create_unique_constraint("uq_raw_items_hash", "raw_items", ["raw_hash"])
    op.create_index("ix_raw_items_status", "raw_items", ["status"])
    op.create_index("ix_raw_items_source_id", "raw_items", ["source_id"])

    op.create_table(
        "story_items",
        sa.Column("story_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stories.id"), primary_key=True),
        sa.Column(
            "raw_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("raw_items.id"), primary_key=True
        ),
        sa.Column("similarity_score", sa.Float, nullable=False, server_default="1.0"),
    )
    op.create_index("ix_story_items_story_id", "story_items", ["story_id"])


def downgrade() -> None:
    op.drop_index("ix_story_items_story_id", table_name="story_items")
    op.drop_table("story_items")
    op.drop_index("ix_raw_items_source_id", table_name="raw_items")
    op.drop_index("ix_raw_items_status", table_name="raw_items")
    op.drop_constraint("uq_raw_items_hash", "raw_items", type_="unique")
    op.drop_table("raw_items")
    op.drop_table("stories")
    op.drop_table("sources")
