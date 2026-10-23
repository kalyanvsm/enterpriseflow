
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'delivered', 'failed')",
            name="ck_outbox_events_status",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="ck_outbox_events_attempts_nonnegative",
        ),
        Index(
            "ix_outbox_events_status_available",
            "status",
            "available_at",
        ),
        Index(
            "ix_outbox_events_org_request_created",
            "organization_id",
            "workflow_request_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workflow_request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workflow_requests.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
