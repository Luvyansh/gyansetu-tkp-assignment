"""Switch knowledge_chunks.embedding from 768-d (Gemini) to 384-d (MiniLM).

Revision ID: 0002_embed_dim_384
Revises: 0001_initial
Create Date: 2026-08-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_embed_dim_384"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Dimension change is incompatible with existing vectors — clear then alter.
    op.execute("UPDATE knowledge_chunks SET embedding = NULL")
    op.execute(
        "ALTER TABLE knowledge_chunks "
        "ALTER COLUMN embedding TYPE vector(384) USING NULL"
    )
    # Drop Gemini-era embed cache rows (wrong model + dim).
    op.execute("DELETE FROM llm_cache WHERE stage_name = 'embedding'")


def downgrade() -> None:
    op.execute("UPDATE knowledge_chunks SET embedding = NULL")
    op.execute(
        "ALTER TABLE knowledge_chunks "
        "ALTER COLUMN embedding TYPE vector(768) USING NULL"
    )
    op.execute("DELETE FROM llm_cache WHERE stage_name = 'embedding'")
