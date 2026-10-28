import asyncio
import logging

from app.core.config import get_settings
from app.services.notifier import LoggingEventNotifier
from app.workers.outbox_worker import run_outbox_loop


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    settings = get_settings()
    notifier = LoggingEventNotifier()

    try:
        asyncio.run(
            run_outbox_loop(
                notifier,
                batch_size=settings.outbox_batch_size,
                poll_interval=settings.outbox_poll_interval,
            )
        )
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Outbox worker interrupted")


if __name__ == "__main__":
    main()
