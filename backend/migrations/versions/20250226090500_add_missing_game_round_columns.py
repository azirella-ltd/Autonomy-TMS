"""Ensure game_rounds has timing columns expected by services

Revision ID: 20250226090500
Revises: 20250226090000
Create Date: 2025-09-26 09:05:00.000000

"""
from __future__ import annotations

from alembic import op
from sqlalchemy import inspect, Column, DateTime

# revision identifiers, used by Alembic.
revision = "20250226090500"
down_revision = "20250226090000"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    insp = inspect(op.get_bind())
    return column in {col["name"] for col in insp.get_columns(table)}


def upgrade() -> None:
    # SQLite does not support multi-column ALTER ... ADD IF NOT EXISTS.
    if not _column_exists("game_rounds", "started_at"):
        op.add_column("game_rounds", Column("started_at", DateTime(), nullable=True))

    if not _column_exists("game_rounds", "ended_at"):
        op.add_column("game_rounds", Column("ended_at", DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind and bind.dialect.name == "sqlite"

    if not is_sqlite and _column_exists("game_rounds", "ended_at"):
        op.drop_column("game_rounds", "ended_at")
    if not is_sqlite and _column_exists("game_rounds", "started_at"):
        op.drop_column("game_rounds", "started_at")
