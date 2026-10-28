import asyncio
import logging

from app.services.notifier import LoggingEventNotifier
from app.workers.outbox_worker import run_outbox_loop


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    notifier = LoggingEventNotifier()

    try:
        asyncio.run(run_outbox_loop(notifier))
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Outbox worker interrupted")


if __name__ == "__main__":
    main()
