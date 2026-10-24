"""Owned native operations against an isolated, disposable Oracle schema."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

import app.db.oracle_connection as oracle
from app.db.oracle_types import database_datetime

_ORACLE_URL = os.environ.get("CODEX_LB_TEST_ORACLE_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _ORACLE_URL, reason="Set CODEX_LB_TEST_ORACLE_URL to an owned Oracle test schema."),
]


@pytest.fixture
async def pool_probe() -> AsyncIterator[tuple[AsyncEngine, Table]]:
    pytest.importorskip("oracledb")
    engine = oracle.create_oracle_async_engine(_ORACLE_URL, pool_size=2, max_overflow=0)
    table = Table(
        f"pool_probe_{uuid4().hex[:12]}",
        MetaData(),
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("recorded_at", database_datetime(), nullable=False),
        Column("created_at", database_datetime(timezone=True), nullable=False, server_default=func.current_timestamp()),
    )
    created = False
    try:
        async with engine.begin() as connection:
            await connection.run_sync(table.create)
            created = True
            await connection.execute(table.insert().values(id=1, recorded_at=datetime(2026, 10, 24, 12, 1, 2, 345678)))
        yield engine, table
    finally:
        try:
            if created:
                async with engine.begin() as connection:
                    await connection.run_sync(table.drop)
        finally:
            await engine.dispose()


async def test_oracle_request_and_background_connections_initialize_utc(pool_probe: tuple[AsyncEngine, Table]) -> None:
    first, table = pool_probe
    second = oracle.create_oracle_async_engine(_ORACLE_URL, pool_size=2, max_overflow=0)
    try:
        for engine in (first, second):
            async with engine.connect() as connection:
                assert await connection.scalar(text("SELECT SESSIONTIMEZONE FROM DUAL")) == "+00:00"
                row = (await connection.execute(select(table))).one()
                assert row.recorded_at == datetime(2026, 10, 24, 12, 1, 2, 345678)
                assert row.created_at.tzinfo == timezone.utc
                before = await connection.scalar(select(func.sys_extract_utc(func.current_timestamp())))
                # Naive UTC binds must compare with the UTC server defaults.
                assert await connection.scalar(select(table.c.id).where(table.c.created_at < before)) == 1
    finally:
        await second.dispose()


async def test_oracle_cancelled_row_lock_wait_recovers_same_pool(
    pool_probe: tuple[AsyncEngine, Table], monkeypatch: pytest.MonkeyPatch
) -> None:
    blocker_engine, table = pool_probe
    monkeypatch.setattr(oracle, "ORACLE_CALL_TIMEOUT_MS", 250)
    victim_engine = oracle.create_oracle_async_engine(_ORACLE_URL, pool_size=1, max_overflow=0)
    attempted = asyncio.Event()
    factory = async_sessionmaker(victim_engine)

    async def wait_for_lock() -> None:
        async with factory() as session:
            attempted.set()
            await session.execute(select(table).with_for_update())

    try:
        # Initialize the victim connection before timing cancellation.
        async with victim_engine.connect() as connection:
            assert await connection.scalar(text("SELECT 1 FROM DUAL")) == 1
        async with blocker_engine.begin() as blocker:
            await blocker.execute(select(table).with_for_update())
            waiter = asyncio.create_task(wait_for_lock())
            try:
                await asyncio.wait_for(attempted.wait(), timeout=3)
                waiter.cancel()
                done, pending = await asyncio.wait({waiter}, timeout=3)
                assert not pending, "cancellation must finish while the competing transaction still holds the lock"
                assert next(iter(done)).cancelled()
                # The same pool must have its only slot available, while the
                # competing row remains locked by a different connection.
                async with victim_engine.connect() as recovered:
                    assert await recovered.scalar(text("SELECT 1 FROM DUAL")) == 1
                assert (await blocker.execute(select(table.c.id))).scalar_one() == 1
            finally:
                await blocker.rollback()
                if not waiter.done():
                    waiter.cancel()
                await asyncio.wait_for(asyncio.gather(waiter, return_exceptions=True), timeout=5)
    finally:
        await victim_engine.dispose()


class _SilentRelay:
    """Hold both traffic directions without closing the established socket."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.forward = asyncio.Event()
        self.forward.set()
        self.intercepted = asyncio.Event()
        self.handlers: set[asyncio.Task[None]] = set()
        self.writers: set[asyncio.StreamWriter] = set()

    def accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.writers.add(writer)
        task = asyncio.create_task(self.serve(reader, writer))
        self.handlers.add(task)
        task.add_done_callback(self.handlers.discard)

    async def pump(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while data := await reader.read(65536):
            if not self.forward.is_set():
                self.intercepted.set()
                await self.forward.wait()
            writer.write(data)
            await writer.drain()

    async def serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        streams = [writer]
        pumps: list[asyncio.Task[None]] = []
        try:
            remote, upstream = await asyncio.open_connection(self.host, self.port)
            streams.append(upstream)
            self.writers.add(upstream)
            pumps = [asyncio.create_task(self.pump(reader, upstream)), asyncio.create_task(self.pump(remote, writer))]
            await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for stream in streams:
                stream.transport.abort()
                self.writers.discard(stream)
            for pump in pumps:
                pump.cancel()
            await asyncio.gather(*pumps, return_exceptions=True)

    async def close(self) -> None:
        self.forward.set()
        for writer in tuple(self.writers):
            writer.transport.abort()
        if self.handlers:
            await asyncio.wait_for(asyncio.gather(*self.handlers, return_exceptions=True), timeout=5)
        assert not self.writers


async def test_oracle_cancelled_blackholed_query_recovers_same_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cancellation may not await RESET indefinitely when the socket is silent."""
    url = make_url(_ORACLE_URL)
    if not url.host or not url.port or not url.query.get("service_name") or url.query.get("protocol", "tcp") != "tcp":
        pytest.skip("Network fault injection requires an explicit TCP host, port and service_name on a local test DB.")
    relay = _SilentRelay(url.host, url.port)
    server = await asyncio.start_server(relay.accept, "127.0.0.1", 0)
    relay_port = server.sockets[0].getsockname()[1]
    monkeypatch.setattr(oracle, "ORACLE_CALL_TIMEOUT_MS", 250)
    engine = oracle.create_oracle_async_engine(
        url.set(host="127.0.0.1", port=relay_port).render_as_string(hide_password=False), pool_size=1, max_overflow=0
    )
    waiter: asyncio.Task | None = None
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT 1 FROM DUAL")) == 1
            relay.forward.clear()
            waiter = asyncio.create_task(connection.execute(text("SELECT 1 FROM DUAL")))
            await asyncio.wait_for(relay.intercepted.wait(), timeout=3)
            waiter.cancel()
            done, pending = await asyncio.wait({waiter}, timeout=3)
            assert not pending, "cancellation must finish before the held traffic is released"
            assert next(iter(done)).cancelled()
        relay.forward.set()
        async with engine.connect() as recovered:
            assert await recovered.scalar(text("SELECT 1 FROM DUAL")) == 1
    finally:
        relay.forward.set()
        if waiter is not None:
            if not waiter.done():
                waiter.cancel()
            await asyncio.wait_for(asyncio.gather(waiter, return_exceptions=True), timeout=5)
        await engine.dispose()
        server.close()
        await server.wait_closed()
        await relay.close()
