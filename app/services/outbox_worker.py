from datetime import timedelta

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.notifier import EventNotifier
from app.services.outbox_dispatcher import dispatch_outbox_events


async def run_outbox_batch(
    notifier: EventNotifier,
    *,
    batch_size: int | None = None,
) -> int:
    """Run one outbox batch with a fresh database session."""
    settings = get_settings()
    effective_batch_size = (
        settings.outbox_batch_size if batch_size is None else batch_size
    )

    async with SessionLocal() as session:
        return await dispatch_outbox_events(
            session,
            notifier,
            batch_size=effective_batch_size,
            max_attempts=settings.outbox_max_attempts,
            retry_delay=timedelta(seconds=settings.outbox_retry_delay),
        )
