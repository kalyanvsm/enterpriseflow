import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.outbox_dispatcher import dispatch_outbox_events
from app.services.outbox_results import RetryOutcome


@pytest.fixture
def claimed_event():
    event = Mock()
    event.id = uuid.uuid4()
    event.claim_token = uuid.uuid4()
    event.event_type = "workflow_request.submitted"
    return event


@pytest.mark.asyncio
async def test_dispatch_marks_successful_delivery(
    monkeypatch,
    claimed_event,
):
    session = AsyncMock()
    notifier = Mock()
    notifier.deliver = AsyncMock()

    async def claim_events(*args, **kwargs):
        return [claimed_event]

    mark_delivered = AsyncMock(return_value=True)
    schedule_retry = AsyncMock()

    monkeypatch.setattr(
        "app.services.outbox_dispatcher.claim_outbox_events",
        claim_events,
    )
    monkeypatch.setattr(
        "app.services.outbox_dispatcher.mark_outbox_event_delivered",
        mark_delivered,
    )
    monkeypatch.setattr(
        "app.services.outbox_dispatcher.schedule_outbox_retry",
        schedule_retry,
    )

    result = await dispatch_outbox_events(session, notifier)

    assert result == 1
    notifier.deliver.assert_awaited_once_with(claimed_event)
    mark_delivered.assert_awaited_once_with(
        session,
        claimed_event.id,
        claim_token=claimed_event.claim_token,
    )
    schedule_retry.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_schedules_retry_after_delivery_error(
    monkeypatch,
    claimed_event,
):
    session = AsyncMock()
    notifier = Mock()
    notifier.deliver = AsyncMock(side_effect=RuntimeError("temporary failure"))

    async def claim_events(*args, **kwargs):
        return [claimed_event]

    mark_delivered = AsyncMock()
    schedule_retry = AsyncMock(return_value=RetryOutcome.RETRY_SCHEDULED)

    monkeypatch.setattr(
        "app.services.outbox_dispatcher.claim_outbox_events",
        claim_events,
    )
    monkeypatch.setattr(
        "app.services.outbox_dispatcher.mark_outbox_event_delivered",
        mark_delivered,
    )
    monkeypatch.setattr(
        "app.services.outbox_dispatcher.schedule_outbox_retry",
        schedule_retry,
    )

    result = await dispatch_outbox_events(
        session,
        notifier,
        max_attempts=3,
        retry_delay=timedelta(seconds=30),
    )

    assert result == 0
    schedule_retry.assert_awaited_once_with(
        session,
        claimed_event.id,
        claim_token=claimed_event.claim_token,
        error="temporary failure",
        max_attempts=3,
        retry_delay=timedelta(seconds=30),
    )
    mark_delivered.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_counts_only_events_marked_delivered(
    monkeypatch,
    claimed_event,
):
    session = AsyncMock()
    notifier = Mock()
    notifier.deliver = AsyncMock()

    async def claim_events(*args, **kwargs):
        return [claimed_event]

    mark_delivered = AsyncMock(return_value=False)

    monkeypatch.setattr(
        "app.services.outbox_dispatcher.claim_outbox_events",
        claim_events,
    )
    monkeypatch.setattr(
        "app.services.outbox_dispatcher.mark_outbox_event_delivered",
        mark_delivered,
    )

    result = await dispatch_outbox_events(session, notifier)

    assert result == 0
    mark_delivered.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_propagates_retry_scheduling_failure(
    monkeypatch,
    claimed_event,
):
    session = AsyncMock()
    notifier = Mock()
    notifier.deliver = AsyncMock(side_effect=RuntimeError("notification unavailable"))

    async def claim_events(*args, **kwargs):
        return [claimed_event]

    monkeypatch.setattr(
        "app.services.outbox_dispatcher.claim_outbox_events",
        claim_events,
    )
    monkeypatch.setattr(
        "app.services.outbox_dispatcher.schedule_outbox_retry",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await dispatch_outbox_events(session, notifier)


@pytest.mark.asyncio
async def test_dispatch_logs_batch_metrics_without_event_payload(
    monkeypatch,
    claimed_event,
    caplog,
):
    import logging

    session = AsyncMock()
    notifier = Mock()
    notifier.deliver = AsyncMock()

    claimed_event.payload = {"secret_content": "do-not-log-this"}
    claimed_event.event_type = "workflow_request.submitted"

    async def claim_events(*args, **kwargs):
        return [claimed_event]

    mark_delivered = AsyncMock(return_value=True)

    monkeypatch.setattr(
        "app.services.outbox_dispatcher.claim_outbox_events",
        claim_events,
    )
    monkeypatch.setattr(
        "app.services.outbox_dispatcher.mark_outbox_event_delivered",
        mark_delivered,
    )

    with caplog.at_level(
        logging.INFO,
        logger="app.services.outbox_dispatcher",
    ):
        result = await dispatch_outbox_events(session, notifier)

    assert result == 1

    batch_record = next(
        record
        for record in caplog.records
        if record.message == "Outbox worker batch completed"
    )

    assert batch_record.claimed_count == 1
    assert batch_record.delivered_count == 1
    assert batch_record.delivery_failed_count == 0
    assert batch_record.retry_scheduled_count == 0
    assert batch_record.claim_conflict_count == 0
    assert batch_record.duration_ms >= 0

    assert "do-not-log-this" not in caplog.text
    assert "secret_content" not in caplog.text


@pytest.mark.asyncio
async def test_dispatch_logs_retry_exhaustion(
    monkeypatch,
    claimed_event,
    caplog,
):
    import logging

    session = AsyncMock()
    notifier = Mock()
    notifier.deliver = AsyncMock(side_effect=RuntimeError("permanent failure"))

    async def claim_events(*args, **kwargs):
        return [claimed_event]

    schedule_retry = AsyncMock(return_value=RetryOutcome.RETRY_EXHAUSTED)

    monkeypatch.setattr(
        "app.services.outbox_dispatcher.claim_outbox_events",
        claim_events,
    )
    monkeypatch.setattr(
        "app.services.outbox_dispatcher.schedule_outbox_retry",
        schedule_retry,
    )

    with caplog.at_level(
        logging.INFO,
        logger="app.services.outbox_dispatcher",
    ):
        result = await dispatch_outbox_events(session, notifier)

    assert result == 0

    batch_record = next(
        record
        for record in caplog.records
        if record.message == "Outbox worker batch completed"
    )
    assert batch_record.claimed_count == 1
    assert batch_record.delivered_count == 0
    assert batch_record.delivery_failed_count == 1
    assert batch_record.retry_scheduled_count == 0
    assert batch_record.retry_exhausted_count == 1
    assert batch_record.claim_conflict_count == 0

    event_record = next(
        record
        for record in caplog.records
        if record.message == "Outbox event retries exhausted"
    )
    assert event_record.event_id == str(claimed_event.id)
    assert event_record.event_type == claimed_event.event_type
    assert event_record.max_attempts == 5
    assert "payload" not in event_record.__dict__


@pytest.mark.asyncio
async def test_dispatch_logs_stale_claim_after_delivery_failure(
    monkeypatch,
    claimed_event,
    caplog,
):
    import logging

    session = AsyncMock()
    notifier = Mock()
    notifier.deliver = AsyncMock(side_effect=RuntimeError("temporary failure"))

    async def claim_events(*args, **kwargs):
        return [claimed_event]

    schedule_retry = AsyncMock(return_value=RetryOutcome.STALE_CLAIM)

    monkeypatch.setattr(
        "app.services.outbox_dispatcher.claim_outbox_events",
        claim_events,
    )
    monkeypatch.setattr(
        "app.services.outbox_dispatcher.schedule_outbox_retry",
        schedule_retry,
    )

    with caplog.at_level(
        logging.INFO,
        logger="app.services.outbox_dispatcher",
    ):
        result = await dispatch_outbox_events(session, notifier)

    assert result == 0

    batch_record = next(
        record
        for record in caplog.records
        if record.message == "Outbox worker batch completed"
    )
    assert batch_record.claimed_count == 1
    assert batch_record.delivered_count == 0
    assert batch_record.delivery_failed_count == 1
    assert batch_record.retry_scheduled_count == 0
    assert batch_record.retry_exhausted_count == 0
    assert batch_record.claim_conflict_count == 1

    event_record = next(
        record
        for record in caplog.records
        if record.message == "Outbox event retry skipped due to stale claim"
    )
    assert event_record.event_id == str(claimed_event.id)
    assert event_record.event_type == claimed_event.event_type
    assert "payload" not in event_record.__dict__
