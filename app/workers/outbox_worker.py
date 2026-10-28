import asyncio
import logging

from app.services.notifier import EventNotifier
from app.services.outbox_worker import run_outbox_batch

logger = logging.getLogger(__name__)


async def run_outbox_loop(
    notifier: EventNotifier,
    *,
    batch_size: int = 10,
    poll_interval: float = 5.0,
) -> None:
    """Process outbox batches until the task is cancelled."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    if poll_interval <= 0:
        raise ValueError("poll_interval must be positive")

    logger.info("Outbox worker started")

    try:
        while True:
            try:
                delivered = await run_outbox_batch(
                    notifier,
                    batch_size=batch_size,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Outbox worker batch failed")
            else:
                if delivered:
                    logger.info(
                        "Outbox worker batch completed",
                        extra={"delivered_count": delivered},
                    )

            await asyncio.sleep(poll_interval)
    finally:
        logger.info("Outbox worker stopped")
