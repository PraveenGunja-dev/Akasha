"""add_chat_feedback_review_fields

Revision ID: 9b7c1f32a4d0
Revises: 398c32532a6e
Create Date: 2026-07-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "9b7c1f32a4d0"
down_revision: Union[str, Sequence[str], None] = "398c32532a6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("chat_feedback"):
        # Older local databases may have chatbot tables from create_all(), while
        # clean Alembic databases may not have them yet. A later migration creates
        # missing chatbot tables without deleting existing data.
        return

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


def downgrade() -> None:
    # Preserve local feedback data on downgrade. Removing these columns can delete
    # reviewed correction metadata, so this migration is intentionally non-destructive.
    pass
