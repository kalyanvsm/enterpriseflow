from app.db.session import SessionLocal
from app.services.notifier import EventNotifier
from app.services.outbox_dispatcher import dispatch_outbox_events


async def run_outbox_batch(
    notifier: EventNotifier,
    *,
    batch_size: int = 10,
) -> int:
    """Run one outbox batch with a fresh database session."""
    async with SessionLocal() as session:
        return await dispatch_outbox_events(
            session,
            notifier,
            batch_size=batch_size,
        )
