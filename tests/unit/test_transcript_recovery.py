from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from app.core.openai.requests import ResponsesRequest
from app.db.models import HttpBridgeSessionState
from app.modules.proxy._service.http_bridge.transcript_recovery import load_transcript_replay
from app.modules.proxy.durable_bridge_coordinator import DurableBridgeLookup, DurableBridgeSessionCoordinator
from tests.simulation.virtual_time import VirtualClock, VirtualScheduler

pytestmark = pytest.mark.unit


def _lookup() -> DurableBridgeLookup:
    return DurableBridgeLookup(
        session_id="session-1",
        canonical_kind="session_header",
        canonical_key="conversation",
        api_key_scope="key-1",
        account_id="owner-1",
        owner_instance_id="instance-1",
        owner_epoch=1,
        lease_expires_at=None,
        state=HttpBridgeSessionState.ACTIVE,
        latest_turn_state=None,
        latest_response_id="resp-1",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [0.0, 2.0, 20.0])
async def test_transcript_load_obeys_deadline_and_cleans_up_timed_out_io(budget: float) -> None:
    clock = VirtualClock()
    scheduler = VirtualScheduler(clock)
    started, finished = asyncio.Event(), asyncio.Event()

    async def read(**kwargs):
        assert kwargs["session_id"] == "session-1"
        assert kwargs["account_id"] == "owner-1"
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    loader = AsyncMock(side_effect=read)
    coordinator = cast(DurableBridgeSessionCoordinator, SimpleNamespace(get_replayable_transcript=loader))
    task = scheduler.create_task(
        load_transcript_replay(
            coordinator,
            lookup=_lookup(),
            payload=ResponsesRequest(model="gpt-5.1", instructions="", input="next", previous_response_id="resp-1"),
            anchor_response_id="resp-1",
            deadline=clock.monotonic() + budget,
            scheduler=scheduler,
            clock=clock,
        )
    )
    if budget:
        await started.wait()
        await scheduler.advance(min(budget, 5.0))
        assert finished.is_set()
    else:
        await scheduler.drain()
        loader.assert_not_awaited()
    assert await task is None
    assert scheduler.pending_timers == 0
    assert all(task.done() for task in scheduler.owned_tasks)


@pytest.mark.asyncio
async def test_transcript_load_propagates_cancellation_and_awaits_cleanup() -> None:
    clock = VirtualClock()
    scheduler = VirtualScheduler(clock)
    started, finished = asyncio.Event(), asyncio.Event()

    async def read(**kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    coordinator = cast(
        DurableBridgeSessionCoordinator, SimpleNamespace(get_replayable_transcript=AsyncMock(side_effect=read))
    )
    task = scheduler.create_task(
        load_transcript_replay(
            coordinator,
            lookup=_lookup(),
            payload=ResponsesRequest(model="gpt-5.1", instructions="", input="next", previous_response_id="resp-1"),
            anchor_response_id="resp-1",
            deadline=30.0,
            scheduler=scheduler,
            clock=clock,
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set()
    assert scheduler.pending_timers == 0
