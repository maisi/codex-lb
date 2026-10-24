"""Prepared ownership operations on an explicitly owned Oracle test schema."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import Column, MetaData, String, Table, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.oracle_connection import create_oracle_async_engine
from app.db.oracle_types import database_datetime
from app.modules.proxy.file_pin_repository import FileAccountPinOwnershipConflict, FileAccountPinRepository

_ORACLE_URL = os.environ.get("CODEX_LB_TEST_ORACLE_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _ORACLE_URL, reason="Set CODEX_LB_TEST_ORACLE_URL to an owned Oracle test schema."),
]


@pytest.fixture
async def oracle_pins() -> AsyncIterator[AsyncEngine]:
    pytest.importorskip("oracledb")
    engine = create_oracle_async_engine(_ORACLE_URL, pool_size=4, max_overflow=0)
    metadata = MetaData()
    # Bounds here isolate testing of ownership; the full Oracle application
    # schema remains blocked on the documented String/empty-value decisions.
    table = Table(
        "file_account_pins",
        metadata,
        Column("file_id", String(128), primary_key=True),
        Column("account_id", String(128), nullable=False),
        Column("expires_at", database_datetime(timezone=True), nullable=False),
    )
    created = False
    try:
        async with engine.begin() as connection:
            exists = await connection.run_sync(lambda connection: inspect(connection).has_table(table.name))
            if exists:
                pytest.fail("Oracle file-pin tests require a schema without an existing file_account_pins table.")
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


async def _claim[Session: AsyncSession](factory: async_sessionmaker[Session], account_id: str) -> str:
    async with factory() as session:
        try:
            await FileAccountPinRepository(session).claim("opaque-file", account_id, ttl_seconds=30)
        except FileAccountPinOwnershipConflict:
            assert not session.in_transaction()
            return "conflict"
        return account_id


async def test_oracle_concurrent_file_claims_cannot_cross_accounts(oracle_pins: AsyncEngine) -> None:
    barrier = asyncio.Barrier(2)

    class SimultaneousFirstReadSession(AsyncSession):
        async def scalar(self, statement, *args: Any, **kwargs: Any) -> Any:
            value = await super().scalar(statement, *args, **kwargs)
            if value is None and "FOR UPDATE" in str(statement).upper():
                # Both sessions observe absence before either inserts. The
                # losing unique-key insert must recover and inspect its owner.
                await asyncio.wait_for(barrier.wait(), timeout=5)
            return value

    factory = async_sessionmaker(oracle_pins, class_=SimultaneousFirstReadSession, expire_on_commit=False)
    # Separate AsyncSessions make the two transactions independent; Oracle
    # coordination must work without the application's SQLite writer section.
    outcomes = await asyncio.gather(_claim(factory, "account-a"), _claim(factory, "account-b"), return_exceptions=True)
    results: list[str] = []
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            raise outcome
        results.append(outcome)

    assert results.count("conflict") == 1
    winner = next(result for result in results if result != "conflict")
    async with factory() as session:
        repository = FileAccountPinRepository(session)
        assert await repository.get_live_account_id("opaque-file") == winner
        assert await repository.get_live_account_ids(["opaque-file", "missing", "opaque-file"]) == {
            "opaque-file": winner
        }


async def test_oracle_same_owner_refresh_and_expired_takeover(oracle_pins: AsyncEngine) -> None:
    factory = async_sessionmaker(oracle_pins, expire_on_commit=False)
    assert await _claim(factory, "account-a") == "account-a"
    async with factory() as session:
        repository = FileAccountPinRepository(session)
        await repository.claim("opaque-file", "account-a", ttl_seconds=60)
        with pytest.raises(FileAccountPinOwnershipConflict):
            await repository.claim("opaque-file", "account-b", ttl_seconds=60)
        assert not session.in_transaction()
        assert await repository.get_live_account_id("opaque-file") == "account-a"
        await session.execute(text("UPDATE file_account_pins SET expires_at = SYSTIMESTAMP - INTERVAL '1' SECOND"))
        await session.commit()
        await repository.claim("opaque-file", "account-b", ttl_seconds=60)
        assert await repository.get_live_account_id("opaque-file") == "account-b"


async def test_oracle_file_pin_ttl_starts_after_row_lock_wait(oracle_pins: AsyncEngine) -> None:
    factory = async_sessionmaker(oracle_pins, expire_on_commit=False)
    assert await _claim(factory, "account-a") == "account-a"
    attempted = asyncio.Event()

    def before_cursor_execute(connection, cursor, statement, parameters, context, executemany) -> None:
        if "FOR UPDATE" in statement.upper():
            attempted.set()

    async with factory() as blocker:
        await blocker.execute(text("SELECT account_id FROM file_account_pins WHERE file_id = 'opaque-file' FOR UPDATE"))
        event.listen(oracle_pins.sync_engine, "before_cursor_execute", before_cursor_execute)

        async def refresh() -> None:
            async with factory() as session:
                await FileAccountPinRepository(session).claim("opaque-file", "account-a", ttl_seconds=2)

        waiter = asyncio.create_task(refresh())
        try:
            await asyncio.wait_for(attempted.wait(), timeout=5)
            assert not waiter.done()
            await asyncio.sleep(2.1)
            await blocker.rollback()
            await asyncio.wait_for(waiter, timeout=10)
        finally:
            event.remove(oracle_pins.sync_engine, "before_cursor_execute", before_cursor_execute)
            await blocker.rollback()
            if not waiter.done():
                waiter.cancel()
            await asyncio.wait_for(asyncio.gather(waiter, return_exceptions=True), timeout=10)
    async with factory() as session:
        remaining = await session.scalar(
            text(
                "SELECT EXTRACT(DAY FROM (expires_at - SYSTIMESTAMP)) * 86400 "
                "+ EXTRACT(HOUR FROM (expires_at - SYSTIMESTAMP)) * 3600 "
                "+ EXTRACT(MINUTE FROM (expires_at - SYSTIMESTAMP)) * 60 "
                "+ EXTRACT(SECOND FROM (expires_at - SYSTIMESTAMP)) FROM file_account_pins"
            )
        )
        assert remaining is not None
        assert 1 < float(remaining) <= 2


async def test_oracle_file_pin_integrity_failure_rolls_back(oracle_pins: AsyncEngine) -> None:
    factory = async_sessionmaker(oracle_pins, expire_on_commit=False)
    async with factory() as session:
        # Oracle turns an empty VARCHAR into NULL: it must fail, never be
        # mistaken for the unique-key race the acquisition retries.
        with pytest.raises(IntegrityError):
            await FileAccountPinRepository(session).claim("opaque-file", "", ttl_seconds=30)
        assert not session.in_transaction()
        assert await FileAccountPinRepository(session).get_live_account_id("opaque-file") is None
