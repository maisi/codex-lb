"""Prepared Oracle scheduler coordination through the existing leader API."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, event, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

import app.core.scheduling.leader_election as leader_module
from app.core.config.settings import Settings
from app.core.scheduling.leader_election import LeaderElection
from app.db.oracle_types import database_datetime

_ORACLE_URL = os.environ.get("CODEX_LB_TEST_ORACLE_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _ORACLE_URL, reason="Set CODEX_LB_TEST_ORACLE_URL to an owned Oracle test schema."),
]


@pytest.fixture
async def oracle_leaders(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncEngine]:
    pytest.importorskip("oracledb")
    engine = create_async_engine(_ORACLE_URL, hide_parameters=True, pool_size=4, max_overflow=0)
    metadata = MetaData()
    table = Table(
        "scheduler_leader",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("leader_id", String(100), nullable=False),
        Column("acquired_at", database_datetime(timezone=True), nullable=False),
        Column("expires_at", database_datetime(timezone=True), nullable=False),
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    monkeypatch.setattr(leader_module, "get_background_session", sessions)
    settings = Settings(leader_election_enabled=True, leader_election_ttl_seconds=5)
    monkeypatch.setattr(leader_module, "get_settings", lambda: settings)
    created = False
    try:
        async with engine.begin() as connection:
            exists = await connection.run_sync(lambda connection: inspect(connection).has_table(table.name))
            if exists:
                pytest.fail("Oracle leader tests require a schema without an existing scheduler_leader table.")
            await connection.run_sync(table.create)
            created = True
        yield engine
    finally:
        try:
            if created:
                async with engine.begin() as connection:
                    await connection.run_sync(table.drop)
        finally:
            await engine.dispose()


async def test_oracle_first_leader_race_has_one_winner(
    oracle_leaders: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    barrier = asyncio.Barrier(2)

    class SimultaneousFirstReadSession(AsyncSession):
        async def scalar(self, statement, *args: Any, **kwargs: Any) -> Any:
            value = await super().scalar(statement, *args, **kwargs)
            if value is None and "FOR UPDATE" in str(statement).upper():
                await asyncio.wait_for(barrier.wait(), timeout=5)
            return value

    factory = async_sessionmaker(oracle_leaders, class_=SimultaneousFirstReadSession, expire_on_commit=False)

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    monkeypatch.setattr(leader_module, "get_background_session", sessions)
    first, second = LeaderElection("first"), LeaderElection("second")
    outcomes = await asyncio.gather(first.try_acquire(), second.try_acquire(), return_exceptions=True)
    results: list[bool] = []
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            raise outcome
        results.append(outcome)
    assert sorted(results) == [False, True]
    winner = first if first.is_leader else second
    follower = second if first.is_leader else first
    assert winner._lease_deadline is not None
    assert 3 < winner._lease_deadline - asyncio.get_running_loop().time() <= 5
    assert follower._lease_deadline is None
    async with oracle_leaders.connect() as connection:
        assert await connection.scalar(text("SELECT leader_id FROM scheduler_leader")) == winner.leader_id


async def test_oracle_leader_refresh_expiry_takeover_and_release(oracle_leaders: AsyncEngine) -> None:
    first, second = LeaderElection("first"), LeaderElection("second")
    assert await first.try_acquire()
    assert not await second.try_acquire()
    assert await first.renew()
    assert await first._renew_lease_row()
    async with oracle_leaders.begin() as connection:
        await connection.execute(text("UPDATE scheduler_leader SET expires_at = SYSTIMESTAMP - INTERVAL '1' SECOND"))
    assert not await first.renew()
    assert not first.is_leader
    assert first._lease_deadline is None
    assert not await first._renew_lease_row()
    assert await second.try_acquire()
    assert await second.release()
    assert not second.is_leader
    async with oracle_leaders.connect() as connection:
        assert await connection.scalar(text("SELECT COUNT(*) FROM scheduler_leader")) == 0


async def test_oracle_renew_waiting_on_row_cannot_resurrect_expired_lease(oracle_leaders: AsyncEngine) -> None:
    leader = LeaderElection("first")
    assert await leader.try_acquire()
    attempted = asyncio.Event()

    def before_cursor_execute(connection, cursor, statement, parameters, context, executemany) -> None:
        if "FOR UPDATE" in statement.upper():
            attempted.set()

    async with oracle_leaders.begin() as blocker:
        await blocker.execute(text("SELECT id FROM scheduler_leader WHERE id = 1 FOR UPDATE"))
        event.listen(oracle_leaders.sync_engine, "before_cursor_execute", before_cursor_execute)
        waiter = asyncio.create_task(leader.renew())
        try:
            await asyncio.wait_for(attempted.wait(), timeout=5)
            assert not waiter.done()
            await blocker.execute(text("UPDATE scheduler_leader SET expires_at = SYSTIMESTAMP - INTERVAL '1' SECOND"))
            await blocker.commit()
            assert not await asyncio.wait_for(waiter, timeout=10)
            assert not leader.is_leader
            assert leader._lease_deadline is None
        finally:
            event.remove(oracle_leaders.sync_engine, "before_cursor_execute", before_cursor_execute)
            await blocker.rollback()
            if not waiter.done():
                waiter.cancel()
            await asyncio.wait_for(asyncio.gather(waiter, return_exceptions=True), timeout=10)


async def test_oracle_same_leader_acquire_grants_full_ttl_after_lock_wait(oracle_leaders: AsyncEngine) -> None:
    leader = LeaderElection("first")
    assert await leader.try_acquire()
    attempted = asyncio.Event()

    def before_cursor_execute(connection, cursor, statement, parameters, context, executemany) -> None:
        if "FOR UPDATE" in statement.upper():
            attempted.set()

    async with oracle_leaders.begin() as blocker:
        await blocker.execute(text("SELECT id FROM scheduler_leader WHERE id = 1 FOR UPDATE"))
        event.listen(oracle_leaders.sync_engine, "before_cursor_execute", before_cursor_execute)
        waiter = asyncio.create_task(leader.try_acquire())
        try:
            await asyncio.wait_for(attempted.wait(), timeout=5)
            await asyncio.sleep(5.1)
            await blocker.commit()
            assert await asyncio.wait_for(waiter, timeout=10)
            assert leader._lease_deadline is not None
            assert 3 < leader._lease_deadline - asyncio.get_running_loop().time() <= 5
        finally:
            event.remove(oracle_leaders.sync_engine, "before_cursor_execute", before_cursor_execute)
            await blocker.rollback()
            if not waiter.done():
                waiter.cancel()
            await asyncio.wait_for(asyncio.gather(waiter, return_exceptions=True), timeout=10)
