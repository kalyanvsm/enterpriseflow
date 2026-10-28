import asyncio
from unittest.mock import AsyncMock

import pytest

from app.workers import outbox_worker


@pytest.mark.asyncio
async def test_worker_loop_retries_after_batch_error(monkeypatch):
    calls = 0
    stopped = asyncio.Event()

    async def fake_run_batch(notifier, *, batch_size):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary database failure")
        stopped.set()
        return 1

    async def fake_sleep(_interval):
        if stopped.is_set():
            raise asyncio.CancelledError

    monkeypatch.setattr(outbox_worker, "run_outbox_batch", fake_run_batch)
    monkeypatch.setattr(outbox_worker.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await outbox_worker.run_outbox_loop(
            AsyncMock(),
            batch_size=3,
            poll_interval=0.01,
        )

    assert calls == 2


@pytest.mark.asyncio
async def test_worker_loop_rejects_invalid_configuration():
    with pytest.raises(ValueError, match="batch_size"):
        await outbox_worker.run_outbox_loop(
            AsyncMock(),
            batch_size=0,
        )

    with pytest.raises(ValueError, match="poll_interval"):
        await outbox_worker.run_outbox_loop(
            AsyncMock(),
            poll_interval=0,
        )


@pytest.mark.asyncio
async def test_worker_loop_stops_when_cancelled(monkeypatch):
    async def fake_run_batch(notifier, *, batch_size):
        return 0

    async def fake_sleep(_interval):
        raise asyncio.CancelledError

    monkeypatch.setattr(outbox_worker, "run_outbox_batch", fake_run_batch)
    monkeypatch.setattr(outbox_worker.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await outbox_worker.run_outbox_loop(
            AsyncMock(),
            poll_interval=0.01,
        )


@pytest.mark.asyncio
async def test_worker_logs_stopped_when_cancelled(monkeypatch, caplog):
    import logging

    async def fake_run_batch(notifier, *, batch_size):
        return 0

    async def fake_sleep(_interval):
        raise asyncio.CancelledError

    monkeypatch.setattr(outbox_worker, "run_outbox_batch", fake_run_batch)
    monkeypatch.setattr(outbox_worker.asyncio, "sleep", fake_sleep)

    with caplog.at_level(logging.INFO, logger="app.workers.outbox_worker"):
        with pytest.raises(asyncio.CancelledError):
            await outbox_worker.run_outbox_loop(
                AsyncMock(),
                poll_interval=0.01,
            )

    assert "Outbox worker started" in caplog.messages
    assert "Outbox worker stopped" in caplog.messages
