"""add pgvector extension and summaries.embedding

Revision ID: b7e2d4f8a3c1
Revises: edf53ce1637a
Create Date: 2026-07-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "b7e2d4f8a3c1"
down_revision: str | Sequence[str] | None = "edf53ce1637a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 1024  # bge-m3


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("summaries", sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True))


def downgrade() -> None:
    op.drop_column("summaries", "embedding")
    # vector 확장은 다른 곳이 쓸 수 있어 남겨둔다.
