"""ensure_chatbot_tables_non_destructive

Revision ID: a4f2c1d9e8b7
Revises: 9b7c1f32a4d0, fd3a008bc83b
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "a4f2c1d9e8b7"
down_revision: Union[str, Sequence[str], None] = ("9b7c1f32a4d0", "fd3a008bc83b")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("metrics_cache"):
        op.create_table(
            "metrics_cache",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("project_id", sa.String(), nullable=False),
            sa.Column("cache_key", sa.String(), nullable=False),
            sa.Column("data", sa.JSON(), nullable=False),
            sa.Column("computed_at", sa.DateTime(), nullable=False),
            sa.Column("p6_synced_at", sa.DateTime(), nullable=True),
            sa.Column("sap_synced_at", sa.DateTime(), nullable=True),
            sa.Column("tc_synced_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_metrics_cache_id", "metrics_cache", ["id"], unique=False)
        op.create_index("ix_metrics_cache_project_id", "metrics_cache", ["project_id"], unique=False)

    if not inspector.has_table("chat_session"):
        op.create_table(
            "chat_session",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("session_id", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=True),
        )
        op.create_index("ix_chat_session_id", "chat_session", ["id"], unique=False)
        op.create_index("ix_chat_session_session_id", "chat_session", ["session_id"], unique=True)

    if not inspector.has_table("chat_message"):
        op.create_table(
            "chat_message",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("session_id", sa.String(), nullable=False),
            sa.Column("role", sa.String(), nullable=False),
            sa.Column("content", sa.String(), nullable=False),
            sa.Column("intent_type", sa.String(), nullable=True),
            sa.Column("project_ids", sa.String(), nullable=True),
            sa.Column("data_domains", sa.String(), nullable=True),
            sa.Column("data_as_of", sa.DateTime(), nullable=True),
            sa.Column("sources_used", sa.JSON(), nullable=True),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["session_id"], ["chat_session.session_id"], ondelete="CASCADE"),
        )
        op.create_index("ix_chat_message_id", "chat_message", ["id"], unique=False)
        op.create_index("ix_chat_message_session_id", "chat_message", ["session_id"], unique=False)

    if not inspector.has_table("chat_feedback"):
        op.create_table(
            "chat_feedback",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("message_id", sa.Integer(), nullable=False),
            sa.Column("feedback_type", sa.String(), nullable=False),
            sa.Column("correction_text", sa.String(), nullable=True),
            sa.Column("project_id", sa.String(), nullable=True),
            sa.Column("question_pattern", sa.String(), nullable=True),
            sa.Column("is_reviewed", sa.Boolean(), nullable=True, server_default=sa.false()),
            sa.Column("trust_level", sa.String(), nullable=True, server_default="unreviewed"),
            sa.Column("reviewed_by", sa.String(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["message_id"], ["chat_message.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_chat_feedback_id", "chat_feedback", ["id"], unique=False)
        op.create_index("ix_chat_feedback_message_id", "chat_feedback", ["message_id"], unique=False)
        op.create_index("ix_chat_feedback_is_reviewed", "chat_feedback", ["is_reviewed"], unique=False)
    else:
        _ensure_chat_feedback_review_columns()


def downgrade() -> None:
    # Intentionally preserve chatbot history, cache, and feedback rows on downgrade.
    pass


def _ensure_chat_feedback_review_columns() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("chat_feedback")}
    if "is_reviewed" not in columns:
        op.add_column("chat_feedback", sa.Column("is_reviewed", sa.Boolean(), nullable=True, server_default=sa.false()))
    if "trust_level" not in columns:
        op.add_column("chat_feedback", sa.Column("trust_level", sa.String(), nullable=True, server_default="unreviewed"))
    if "reviewed_by" not in columns:
        op.add_column("chat_feedback", sa.Column("reviewed_by", sa.String(), nullable=True))
    if "reviewed_at" not in columns:
        op.add_column("chat_feedback", sa.Column("reviewed_at", sa.DateTime(), nullable=True))

    indexes = {index["name"] for index in inspector.get_indexes("chat_feedback")}
    if "ix_chat_feedback_is_reviewed" not in indexes:
        op.create_index("ix_chat_feedback_is_reviewed", "chat_feedback", ["is_reviewed"], unique=False)
