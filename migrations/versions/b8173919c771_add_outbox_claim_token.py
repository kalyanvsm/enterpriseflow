"""add outbox claim token

Revision ID: b8173919c771
Revises: ae6cfb783f0a
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8173919c771"
down_revision: str | Sequence[str] | None = "ae6cfb783f0a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a token identifying the current outbox claim."""
    op.add_column(
        "outbox_events",
        sa.Column("claim_token", sa.Uuid(), nullable=True),
    )


def downgrade() -> None:
    """Remove the outbox claim token."""
    op.drop_column("outbox_events", "claim_token")
