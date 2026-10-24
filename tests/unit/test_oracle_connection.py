from __future__ import annotations

import asyncio
from typing import cast

import pytest

from app.db.oracle_connection import _own_native_operation


@pytest.mark.parametrize("fail", [False, True])
async def test_native_operation_finishes_before_caller_cancellation_propagates(fail: bool) -> None:
    started = asyncio.Event()
    finish = asyncio.Event()
    completed = False

    @_own_native_operation
    async def operation() -> int:
        nonlocal completed
        started.set()
        await finish.wait()
        completed = True
        if fail:
            raise TimeoutError("native timeout")
        return 7

    caller = asyncio.create_task(operation())
    await started.wait()
    caller.cancel()
    await asyncio.sleep(0)
    caller.cancel()
    await asyncio.sleep(0)
    assert not caller.done()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert completed


async def test_native_timeout_without_cancellation_remains_an_error() -> None:
    error = TimeoutError("native timeout")

    @_own_native_operation
    async def operation() -> int:
        raise error

    with pytest.raises(TimeoutError) as caught:
        await operation()
    assert caught.value is error


async def test_native_operation_preserves_successful_result() -> None:
    @_own_native_operation
    async def operation(value: int) -> int:
        return value

    assert await operation(7) == 7


def test_oversized_oracle_pool_fails_before_opening_a_connection() -> None:
    from app.db.oracle_connection import create_oracle_async_engine
    from app.db.oracle_preflight import OraclePreflightError

    with pytest.raises(OraclePreflightError, match="no operational reserve"):
        create_oracle_async_engine(
            "oracle+oracledb://user:password@host/?service_name=service", pool_size=15, max_overflow=0
        )


def test_request_and_background_paths_use_native_oracle_pools(monkeypatch: pytest.MonkeyPatch) -> None:
    from sqlalchemy.ext.asyncio import AsyncEngine

    import app.db.session as sessions

    created: list[tuple[str, int, int]] = []
    engine = cast(AsyncEngine, object())
    url = "oracle+oracledb://user:password@host/?service_name=service"

    def create(database_url: str, *, pool_size: int, max_overflow: int) -> AsyncEngine:
        created.append((database_url, pool_size, max_overflow))
        return engine

    monkeypatch.setattr(sessions, "require_supported_database_backend", lambda *args, **kwargs: None)
    monkeypatch.setattr(sessions, "create_oracle_async_engine", create)
    monkeypatch.setattr(sessions, "_background_engine", None)
    monkeypatch.setattr(sessions, "_background_session_factory", None)
    assert sessions._create_main_engine(url) is engine
    sessions.init_background_db(url)
    assert sessions._background_engine is engine
    assert created == [(url, sessions._settings.database_pool_size, sessions._settings.database_max_overflow)] * 2
