
"""make audit logs append only

Revision ID: 936f1cce06c3
Revises: ccbfb5c5aef8
"""

from collections.abc import Sequence

from alembic import op

revision: str = "936f1cce06c3"
down_revision: str | Sequence[str] | None = "ccbfb5c5aef8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION prevent_audit_log_mutation()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        BEGIN
            RAISE EXCEPTION 'Audit logs are append-only: UPDATE, DELETE are forbidden';
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE TRIGGER audit_logs_append_only
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_log_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS prevent_audit_log_mutation()"
    )
