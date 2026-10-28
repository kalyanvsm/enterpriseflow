import logging
import uuid
from unittest.mock import Mock

import pytest

from app.models.outbox_event import OutboxEvent
from app.services.notifier import LoggingEventNotifier


@pytest.mark.asyncio
async def test_logging_notifier_logs_event_metadata(caplog):
    event = Mock(spec=OutboxEvent)
    event.id = uuid.uuid4()
    event.event_type = "workflow_request.submitted"
    event.organization_id = uuid.uuid4()
    event.workflow_request_id = uuid.uuid4()
    event.payload = {"secret": "must-not-be-logged"}

    notifier = LoggingEventNotifier()

    with caplog.at_level(logging.INFO, logger="app.services.notifier"):
        await notifier.deliver(event)

    assert len(caplog.records) == 1

    record = caplog.records[0]
    assert record.name == "app.services.notifier"
    assert record.getMessage() == "Outbox event delivered to development notifier"
    assert record.event_id == str(event.id)
    assert record.event_type == event.event_type
    assert record.organization_id == str(event.organization_id)
    assert record.workflow_request_id == str(event.workflow_request_id)
    assert "payload" not in record.__dict__
    assert "must-not-be-logged" not in record.getMessage()


@pytest.mark.asyncio
async def test_logging_notifier_uses_stable_event_id_on_repeated_delivery(
    caplog,
):
    event = Mock(spec=OutboxEvent)
    event.id = uuid.uuid4()
    event.event_type = "workflow_request.submitted"
    event.organization_id = uuid.uuid4()
    event.workflow_request_id = uuid.uuid4()
    event.payload = {"title": "Example request"}

    notifier = LoggingEventNotifier()

    with caplog.at_level(logging.INFO, logger="app.services.notifier"):
        await notifier.deliver(event)
        await notifier.deliver(event)

    records = [
        record
        for record in caplog.records
        if record.message == "Outbox event delivered to development notifier"
    ]

    assert len(records) == 2
    assert records[0].event_id == str(event.id)
    assert records[1].event_id == str(event.id)
