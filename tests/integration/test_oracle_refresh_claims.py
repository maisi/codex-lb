"""Prepared Oracle refresh ownership through the existing coordinator API."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy import Column, MetaData, String, Table, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.modules.accounts.refresh_claims as claim_module
from app.db.oracle_connection import ORACLE_CALL_TIMEOUT_MS, create_oracle_async_engine
from app.db.oracle_types import database_datetime
from app.modules.accounts.refresh_claims import RefreshClaimCoordinator

_ORACLE_URL = os.environ.get("CODEX_LB_TEST_ORACLE_URL", "")
_OWNER_A = "a" * 64
_OWNER_B = "b" * 64
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _ORACLE_URL, reason="Set CODEX_LB_TEST_ORACLE_URL to an owned Oracle test schema."),
]


@pytest.fixture
async def oracle_claims(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncEngine]:
    pytest.importorskip("oracledb")
    engine = create_oracle_async_engine(_ORACLE_URL, pool_size=4, max_overflow=0)
    table = Table(
        "account_refresh_claims",
        MetaData(),
        Column("account_id", String(128), primary_key=True),
        Column("claimed_by", String(128), nullable=False),
        Column("claimed_at", database_datetime(), nullable=False),
        Column("claim_expires_at", database_datetime(), nullable=False),
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            await session.execute(text("ALTER SESSION SET TIME_ZONE = '-04:00'"))
            yield session

    @asynccontextmanager
    async def no_sqlite_writer() -> AsyncIterator[None]:
        # The ambient test app uses SQLite. A real Oracle deployment's writer
        # section is a no-op; do not serialize the two Oracle sessions locally.
        yield

    monkeypatch.setattr(claim_module, "get_background_session", sessions)
    monkeypatch.setattr(claim_module, "sqlite_writer_section", no_sqlite_writer)
    created = False
    try:
        async with engine.begin() as connection:
            exists = await connection.run_sync(lambda connection: inspect(connection).has_table(table.name))
            if exists:
                pytest.fail("Oracle refresh tests require no existing account_refresh_claims table.")
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


async def test_oracle_refresh_first_claim_race_has_one_owner(
    oracle_claims: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    barrier = asyncio.Barrier(2)

    class SimultaneousFirstReadSession(AsyncSession):
        async def scalar(self, statement, *args: Any, **kwargs: Any) -> Any:
            value = await super().scalar(statement, *args, **kwargs)
            if value is None and "FOR UPDATE" in str(statement).upper():
                await asyncio.wait_for(barrier.wait(), timeout=5)
            return value

    factory = async_sessionmaker(oracle_claims, class_=SimultaneousFirstReadSession, expire_on_commit=False)

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    monkeypatch.setattr(claim_module, "get_background_session", sessions)
    first, second = RefreshClaimCoordinator(claimant_id="first"), RefreshClaimCoordinator(claimant_id="second")
    outcomes = await asyncio.gather(
        first.try_acquire("account", ttl_seconds=30, owner=_OWNER_A),
        second.try_acquire("account", ttl_seconds=30, owner=_OWNER_B),
        return_exceptions=True,
    )
    results: list[bool] = []
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            raise outcome
        results.append(outcome)
    assert sorted(results) == [False, True]
    claim = await first.current_claim("account")
    assert claim is not None
    assert claim.claimed_by == ("first#" + _OWNER_A[:16] if results[0] else "second#" + _OWNER_B[:16])
    # No lock may survive return: the caller can now exchange an upstream token.
    async with oracle_claims.begin() as connection:
        await connection.execute(text("SELECT account_id FROM account_refresh_claims FOR UPDATE NOWAIT"))


async def test_oracle_refresh_exact_owner_release_and_reentry(oracle_claims: AsyncEngine) -> None:
    coordinator = RefreshClaimCoordinator(claimant_id="first")
    assert await coordinator.try_acquire("account", ttl_seconds=30, owner=_OWNER_A)
    assert await coordinator.try_acquire("account", ttl_seconds=30, owner=_OWNER_A)
    assert not await coordinator.try_acquire("account", ttl_seconds=30, owner=_OWNER_B)
    await coordinator.release("account", owner=_OWNER_B)
    claim = await coordinator.current_claim("account")
    assert claim is not None
    assert claim.claimed_by == "first#" + _OWNER_A[:16]
    await coordinator.release("account", owner=_OWNER_A)
    assert await coordinator.current_claim("account") is None
    assert await coordinator.try_acquire("account", ttl_seconds=30, owner=_OWNER_B)


async def test_oracle_refresh_expiry_uses_utc_and_foreign_release_is_noop(oracle_claims: AsyncEngine) -> None:
    first, second = RefreshClaimCoordinator(claimant_id="first"), RefreshClaimCoordinator(claimant_id="second")
    async with oracle_claims.connect() as connection:
        before = await connection.scalar(text("SELECT SYS_EXTRACT_UTC(SYSTIMESTAMP) FROM DUAL"))
    assert await first.try_acquire("account", ttl_seconds=30, owner=_OWNER_A)
    await second.release("account", owner=_OWNER_A)
    claim = await first.current_claim("account")
    assert claim is not None
    async with oracle_claims.begin() as connection:
        after = await connection.scalar(text("SELECT SYS_EXTRACT_UTC(SYSTIMESTAMP) FROM DUAL"))
        assert before <= claim.claimed_at <= after
        assert claim.claimed_at.tzinfo is None
        assert claim.claimed_by.startswith("first#")
        await connection.execute(
            text(
                "UPDATE account_refresh_claims SET claim_expires_at = "
                "SYS_EXTRACT_UTC(SYSTIMESTAMP) - INTERVAL '1' SECOND"
            )
        )
    assert await second.try_acquire("account", ttl_seconds=30, owner=_OWNER_B)
    await first.release("account", owner=_OWNER_A)
    claim = await second.current_claim("account")
    assert claim is not None and claim.claimed_by == "second#" + _OWNER_B[:16]


async def test_oracle_refresh_ttl_is_fresh_after_lock_wait(oracle_claims: AsyncEngine) -> None:
    coordinator = RefreshClaimCoordinator(claimant_id="first")
    assert await coordinator.try_acquire("account", ttl_seconds=30, owner=_OWNER_A)
    attempted = asyncio.Event()

    def before_cursor_execute(connection, cursor, statement, parameters, context, executemany) -> None:
        if "FOR UPDATE" in statement.upper():
            attempted.set()

    async with oracle_claims.begin() as blocker:
        await blocker.execute(text("SELECT account_id FROM account_refresh_claims FOR UPDATE"))
        event.listen(oracle_claims.sync_engine, "before_cursor_execute", before_cursor_execute)
        waiter = asyncio.create_task(coordinator.try_acquire("account", ttl_seconds=2, owner=_OWNER_A))
        try:
            await asyncio.wait_for(attempted.wait(), timeout=5)
            await asyncio.sleep(2.1)
            await blocker.commit()
            assert await asyncio.wait_for(waiter, timeout=10)
        finally:
            event.remove(oracle_claims.sync_engine, "before_cursor_execute", before_cursor_execute)
            await blocker.rollback()
            if not waiter.done():
                waiter.cancel()
            await asyncio.wait_for(asyncio.gather(waiter, return_exceptions=True), timeout=10)
    claim = await coordinator.current_claim("account")
    assert claim is not None
    async with oracle_claims.connect() as connection:
        now = await connection.scalar(text("SELECT SYS_EXTRACT_UTC(SYSTIMESTAMP) FROM DUAL"))
    assert 1 < (claim.claim_expires_at - now).total_seconds() <= 2


async def test_oracle_refresh_non_unique_integrity_failure_cleans_session(oracle_claims: AsyncEngine) -> None:
    coordinator = RefreshClaimCoordinator(claimant_id="first")
    with pytest.raises(IntegrityError):
        await coordinator.try_acquire("", ttl_seconds=30, owner=_OWNER_A)
    async with oracle_claims.connect() as connection:
        assert await connection.scalar(text("SELECT COUNT(*) FROM account_refresh_claims")) == 0


async def test_oracle_refresh_first_insert_wait_gets_full_ttl_after_contender_rollback(
    oracle_claims: AsyncEngine,
) -> None:
    coordinator = RefreshClaimCoordinator(claimant_id="winner")
    attempted = asyncio.Event()

    def before_cursor_execute(connection, cursor, statement, parameters, context, executemany) -> None:
        if statement.upper().startswith("INSERT INTO ACCOUNT_REFRESH_CLAIMS"):
            attempted.set()

    async with oracle_claims.begin() as blocker:
        await blocker.execute(
            text(
                "INSERT INTO account_refresh_claims (account_id, claimed_by, claimed_at, claim_expires_at) "
                "VALUES ('account', 'rolling-back', SYS_EXTRACT_UTC(SYSTIMESTAMP), "
                "SYS_EXTRACT_UTC(SYSTIMESTAMP) + INTERVAL '30' SECOND)"
            )
        )
        event.listen(oracle_claims.sync_engine, "before_cursor_execute", before_cursor_execute)
        waiter = asyncio.create_task(coordinator.try_acquire("account", ttl_seconds=2, owner=_OWNER_A))
        try:
            await asyncio.wait_for(attempted.wait(), timeout=5)
            await asyncio.sleep(2.1)
            assert not waiter.done()
            await blocker.rollback()
            assert await asyncio.wait_for(waiter, timeout=10)
        finally:
            event.remove(oracle_claims.sync_engine, "before_cursor_execute", before_cursor_execute)
            await blocker.rollback()
            if not waiter.done():
                waiter.cancel()
            await asyncio.wait_for(asyncio.gather(waiter, return_exceptions=True), timeout=10)

    claim = await coordinator.current_claim("account")
    assert claim is not None and claim.claimed_by == "winner#" + _OWNER_A[:16]
    async with oracle_claims.connect() as connection:
        now = await connection.scalar(text("SELECT SYS_EXTRACT_UTC(SYSTIMESTAMP) FROM DUAL"))
    assert 1 < (claim.claim_expires_at - now).total_seconds() <= 2


async def test_oracle_refresh_cancellation_releases_connection(oracle_claims: AsyncEngine) -> None:
    coordinator = RefreshClaimCoordinator(claimant_id="first")
    assert await coordinator.try_acquire("account", ttl_seconds=30, owner=_OWNER_A)
    attempted = asyncio.Event()

    def before_cursor_execute(connection, cursor, statement, parameters, context, executemany) -> None:
        if "FOR UPDATE" in statement.upper():
            attempted.set()

    async with oracle_claims.begin() as blocker:
        await blocker.execute(text("SELECT account_id FROM account_refresh_claims FOR UPDATE"))
        event.listen(oracle_claims.sync_engine, "before_cursor_execute", before_cursor_execute)
        waiter = asyncio.create_task(coordinator.try_acquire("account", ttl_seconds=30, owner=_OWNER_B))
        try:
            await asyncio.wait_for(attempted.wait(), timeout=5)
            waiter.cancel()
            # Native timeout and recovery each have one round-trip budget.
            # Caller cancellation never interrupts native RESET.
            done, pending = await asyncio.wait({waiter}, timeout=2 * ORACLE_CALL_TIMEOUT_MS / 1000 + 5)
            assert not pending, "Cancellation must finish while the competing row remains locked"
            assert next(iter(done)).cancelled()
        finally:
            event.remove(oracle_claims.sync_engine, "before_cursor_execute", before_cursor_execute)
            # Release our own competing transaction before awaiting cleanup,
            # including when native cancellation fails the bounded assertion.
            await blocker.rollback()
            if not waiter.done():
                waiter.cancel()
            await asyncio.wait_for(asyncio.gather(waiter, return_exceptions=True), timeout=10)
    claim = await coordinator.current_claim("account")
    assert claim is not None and claim.claimed_by == "first#" + _OWNER_A[:16]
