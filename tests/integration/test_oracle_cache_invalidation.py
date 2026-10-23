"""Prepared Oracle invalidation through the existing replica poller API."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
from sqlalchemy import CursorResult, Table, inspect, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.cache.invalidation import NAMESPACE_SETTINGS, CacheInvalidationPoller
from app.db.models import CacheInvalidation

_ORACLE_URL = os.environ.get("CODEX_LB_TEST_ORACLE_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _ORACLE_URL, reason="Set CODEX_LB_TEST_ORACLE_URL to an owned Oracle test schema."),
]


@pytest.fixture
async def oracle_invalidations() -> AsyncIterator[AsyncEngine]:
    pytest.importorskip("oracledb")
    engine = create_async_engine(_ORACLE_URL, hide_parameters=True, pool_size=4, max_overflow=0)
    table = cast(Table, CacheInvalidation.__table__)
    created = False
    try:
        async with engine.begin() as connection:
            exists = await connection.run_sync(lambda connection: inspect(connection).has_table(table.name))
            if exists:
                pytest.fail("Oracle invalidation tests require no existing cache_invalidation table.")
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


async def _version(engine: AsyncEngine) -> int | None:
    async with engine.connect() as connection:
        return await connection.scalar(
            select(CacheInvalidation.version).where(CacheInvalidation.namespace == NAMESPACE_SETTINGS)
        )


async def test_oracle_invalidation_first_insert_race_counts_both_changes(oracle_invalidations: AsyncEngine) -> None:
    barrier = asyncio.Barrier(2)

    class SimultaneousFirstUpdateSession(AsyncSession):
        async def execute(self, statement, *args: Any, **kwargs: Any) -> Any:
            result = await super().execute(statement, *args, **kwargs)
            if (
                str(statement).upper().startswith("UPDATE CACHE_INVALIDATION")
                and cast(CursorResult, result).rowcount == 0
            ):
                await asyncio.wait_for(barrier.wait(), timeout=5)
            return result

    factory = async_sessionmaker(oracle_invalidations, class_=SimultaneousFirstUpdateSession, expire_on_commit=False)
    first, second = CacheInvalidationPoller(factory), CacheInvalidationPoller(factory)
    outcomes = await asyncio.gather(
        first.bump(NAMESPACE_SETTINGS), second.bump(NAMESPACE_SETTINGS), return_exceptions=True
    )
    assert outcomes == [True, True]
    assert await _version(oracle_invalidations) == 2


async def test_oracle_invalidation_existing_version_has_no_lost_increments(oracle_invalidations: AsyncEngine) -> None:
    factory = async_sessionmaker(oracle_invalidations, expire_on_commit=False)
    first, second = CacheInvalidationPoller(factory), CacheInvalidationPoller(factory)
    assert await first.bump(NAMESPACE_SETTINGS)
    # Fan-out is bounded by both the four tasks and the four-connection pool.
    outcomes = await asyncio.gather(
        first.bump(NAMESPACE_SETTINGS),
        second.bump(NAMESPACE_SETTINGS),
        first.bump(NAMESPACE_SETTINGS),
        second.bump(NAMESPACE_SETTINGS),
        return_exceptions=True,
    )
    assert outcomes == [True] * 4
    assert await _version(oracle_invalidations) == 5


async def test_oracle_invalidation_failed_commit_rolls_back_before_retry(oracle_invalidations: AsyncEngine) -> None:
    failed = False

    class FailFirstCommitSession(AsyncSession):
        async def commit(self) -> None:
            nonlocal failed
            if not failed:
                failed = True
                raise OperationalError("injected commit failure", None, RuntimeError("test only"))
            await super().commit()

    factory = async_sessionmaker(oracle_invalidations, class_=FailFirstCommitSession, expire_on_commit=False)
    poller = CacheInvalidationPoller(factory)
    assert await poller.bump(NAMESPACE_SETTINGS)
    assert failed
    assert await _version(oracle_invalidations) == 1
    assert await poller.bump(NAMESPACE_SETTINGS)
    assert await _version(oracle_invalidations) == 2


async def test_oracle_invalidation_local_acknowledgement_preserves_peer_delivery(
    oracle_invalidations: AsyncEngine,
) -> None:
    factory = async_sessionmaker(oracle_invalidations, expire_on_commit=False)
    origin, peer = CacheInvalidationPoller(factory), CacheInvalidationPoller(factory)
    origin_calls, peer_calls = [], []
    origin.on_invalidation(NAMESPACE_SETTINGS, lambda: origin_calls.append("origin"))
    peer.on_invalidation(NAMESPACE_SETTINGS, lambda: peer_calls.append("peer"))
    await origin.initialize()
    await peer.initialize()
    assert await origin.bump_local(NAMESPACE_SETTINGS)
    assert await origin._poll_once()
    assert await peer._poll_once()
    assert origin_calls == []
    assert peer_calls == ["peer"]


async def test_oracle_invalidation_uncertain_commit_keeps_peer_delivery(oracle_invalidations: AsyncEngine) -> None:
    failed = False

    class UncertainFirstCommitSession(AsyncSession):
        async def commit(self) -> None:
            nonlocal failed
            await super().commit()
            if not failed:
                failed = True
                raise OperationalError("injected lost commit acknowledgement", None, RuntimeError("test only"))

    factory = async_sessionmaker(oracle_invalidations, expire_on_commit=False)
    uncertain_factory = async_sessionmaker(
        oracle_invalidations, class_=UncertainFirstCommitSession, expire_on_commit=False
    )
    origin, peer = CacheInvalidationPoller(uncertain_factory), CacheInvalidationPoller(factory)
    peer_calls = []
    peer.on_invalidation(NAMESPACE_SETTINGS, lambda: peer_calls.append("peer"))
    await peer.initialize()
    assert await origin.bump(NAMESPACE_SETTINGS)
    assert failed
    assert await _version(oracle_invalidations) == 2
    assert await peer._poll_once()
    assert peer_calls == ["peer"]
    assert await peer._poll_once()
    assert peer_calls == ["peer"]
