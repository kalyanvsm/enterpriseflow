from datetime import timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from app.services import outbox_worker


@pytest.mark.asyncio
async def test_run_outbox_batch_uses_session_and_dispatches(monkeypatch):
    session = AsyncMock()
    session_context = Mock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=False)

    session_local = Mock(return_value=session_context)
    monkeypatch.setattr(outbox_worker, "SessionLocal", session_local)

    notifier = Mock()
    dispatch = AsyncMock(return_value=3)
    monkeypatch.setattr(
        outbox_worker,
        "dispatch_outbox_events",
        dispatch,
    )

    result = await outbox_worker.run_outbox_batch(
        notifier,
        batch_size=7,
    )

    assert result == 3
    session_local.assert_called_once_with()
    dispatch.assert_awaited_once_with(
        session,
        notifier,
        batch_size=7,
        max_attempts=5,
        retry_delay=timedelta(seconds=60),
    )
    session_context.__aexit__.assert_awaited_once()
