from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table, event, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import QueuePool

import app.db.session as db_session
from app.core.config.settings import get_settings
from app.core.scheduling import leader_election as leader_module
from app.db.models import SchedulerLeader

pytestmark = pytest.mark.integration


async def test_oracle_lease_operations_survive_exhausted_background_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Exercise Oracle startup wiring with real bounded pools and lease SQL,
    # substituting only the driver so this test never contacts an Oracle server.
    oracle_url = "oracle+oracledb://user:password@database.invalid/?service_name=test"
    sqlite_url = f"sqlite+aiosqlite:///{tmp_path / 'leases.db'}"
    created: list[tuple[AsyncEngine, int, int]] = []
    disposed: set[AsyncEngine] = set()

    def create(database_url: str, *, pool_size: int, max_overflow: int) -> AsyncEngine:
        assert database_url == oracle_url
        engine = create_async_engine(sqlite_url, pool_size=pool_size, max_overflow=max_overflow, pool_timeout=0.1)
        db_session._configure_sqlite_engine(engine.sync_engine, enable_wal=True)
        event.listen(engine.sync_engine, "engine_disposed", lambda _engine: disposed.add(engine))
        created.append((engine, pool_size, max_overflow))
        return engine

    settings = get_settings().model_copy(
        update={
            "database_url": oracle_url,
            "database_pool_size": 4,
            "database_max_overflow": 0,
            "leader_election_enabled": True,
            "leader_election_ttl_seconds": 60,
        }
    )
    monkeypatch.setattr(db_session, "create_oracle_async_engine", create)
    monkeypatch.setattr(db_session, "_settings", settings)
    monkeypatch.setattr(db_session, "_background_engine", None)
    monkeypatch.setattr(db_session, "_background_session_factory", None)
    monkeypatch.setattr(db_session, "_leader_engine", None, raising=False)
    monkeypatch.setattr(db_session, "_leader_session_factory", None, raising=False)
    monkeypatch.setattr(leader_module, "get_settings", lambda: settings)
    main = db_session._create_main_engine(oracle_url)
    monkeypatch.setattr(db_session, "engine", main)
    db_session.init_background_db(oracle_url)
    background = db_session._background_engine
    assert background is not None
    try:
        async with main.begin() as connection:
            await connection.run_sync(cast(Table, SchedulerLeader.__table__).create)
        async with AsyncExitStack() as stack:
            # Exhaust both general-purpose pools, not just the background pool.
            for engine in (main, background):
                for _ in range(4):
                    connection = await stack.enter_async_context(engine.connect())
                    assert await connection.scalar(text("SELECT 1")) == 1
                assert cast(QueuePool, engine.pool).checkedout() == 4
            leader = leader_module.LeaderElection("isolated-leader")
            assert await asyncio.wait_for(leader.try_acquire(), timeout=1)
            assert await asyncio.wait_for(leader.renew(), timeout=1)
            assert await asyncio.wait_for(leader.release(), timeout=1)
            assert await asyncio.wait_for(leader.try_acquire(), timeout=1)
            # Error cleanup must also return the only coordination connection.
            with pytest.raises(RuntimeError, match="controlled failure"):
                async with db_session.get_leader_session() as session:
                    assert await session.scalar(text("SELECT 1")) == 1
                    raise RuntimeError("controlled failure")
            assert await asyncio.wait_for(leader.renew(), timeout=1)
            assert await asyncio.wait_for(leader.release(), timeout=1)
        assert [(size, overflow) for _engine, size, overflow in created] == [(4, 0), (4, 0), (1, 0)]
        assert all(cast(QueuePool, engine.pool).checkedout() == 0 for engine, _size, _overflow in created)
    finally:
        try:
            await db_session.close_db()
            assert disposed == {engine for engine, _size, _overflow in created}
        finally:
            # Clean up even if the shutdown assertion detects a missing pool.
            for engine, _size, _overflow in created:
                if engine not in disposed:
                    await engine.dispose()
