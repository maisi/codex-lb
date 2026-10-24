"""Native Thin connections with owned I/O, wallet support and UTC sessions."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import cache, wraps
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, cast

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.utils.shared_future import _await_result_deferring_cancellation
from app.db.oracle_preflight import OracleSessionBudget, _connection_params, _oracle_url

if TYPE_CHECKING:
    import oracledb

# A stalled round trip plus native recovery can consume twice this bound.
# Keep it below the application's request deadline so disconnect cleanup does
# not enter the driver's unbounded cancellation-first BREAK/RESET path (#623).
# Initial LOB writes on Autonomous Free can exceed five seconds. Fifteen
# seconds allows those operations while keeping timeout recovery bounded.
ORACLE_CALL_TIMEOUT_MS = 15_000
# DDL and the first parse of a wide baseline insert can be substantially slower
# on Autonomous Free. These synchronous connections never serve requests.
ORACLE_MIGRATION_CALL_TIMEOUT_MS = 60_000
ORACLE_CONNECT_TIMEOUT_SECONDS = 10.0
_POOL_TIMEOUT_SECONDS = 30.0
_POOL_RECYCLE_SECONDS = 1800
_P = ParamSpec("_P")
_T = TypeVar("_T")


@dataclass(frozen=True)
class _OperationOutcome[T]:
    value: T | None = None
    error: Exception | None = None


def _own_native_operation(function: Callable[_P, Awaitable[_T]]) -> Callable[_P, Awaitable[_T]]:
    """Join native I/O before propagating a request cancellation.

    Oracle bounds native-timeout recovery, but caller cancellation can enter
    an unbounded RESET receive. Shield only the driver operation, retaining
    ownership until its timeout/recovery finishes. SQLAlchemy then sees the
    original cancellation and can invalidate/rollback without racing a query.
    An interrupted commit is never replayed: its outcome may be unknown.
    """

    @wraps(function)
    async def _owned(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        async def _complete() -> _OperationOutcome[_T]:
            try:
                return _OperationOutcome(value=await function(*args, **kwargs))
            except Exception as exc:
                # Preserve a pending caller cancellation even when native I/O
                # ends with a timeout/disconnect during its recovery.
                return _OperationOutcome(error=exc)

        outcome, cancellation = await _await_result_deferring_cancellation(_complete())
        if cancellation is not None:
            raise cancellation
        if outcome.error is not None:
            raise outcome.error
        return cast(_T, outcome.value)

    return _owned


@cache
def _owned_connection_class() -> type[oracledb.AsyncConnection]:
    # Keep the optional driver out of SQLite/PostgreSQL import paths.
    import oracledb

    class _OwnedCursor(oracledb.AsyncCursor):
        execute = _own_native_operation(oracledb.AsyncCursor.execute)
        executemany = _own_native_operation(oracledb.AsyncCursor.executemany)
        fetchone = _own_native_operation(oracledb.AsyncCursor.fetchone)
        fetchmany = _own_native_operation(oracledb.AsyncCursor.fetchmany)
        fetchall = _own_native_operation(oracledb.AsyncCursor.fetchall)

    class _OwnedConnection(oracledb.AsyncConnection):
        close = _own_native_operation(oracledb.AsyncConnection.close)
        commit = _own_native_operation(oracledb.AsyncConnection.commit)
        rollback = _own_native_operation(oracledb.AsyncConnection.rollback)
        ping = _own_native_operation(oracledb.AsyncConnection.ping)

        def cursor(self, scrollable: bool = False) -> oracledb.AsyncCursor:
            # The driver's shared BaseCursor constructor annotates only its
            # synchronous Connection, though AsyncCursor accepts this class.
            return _OwnedCursor(cast(Any, self), scrollable)

    return _OwnedConnection


async def connect_oracle_async(database_url: str) -> oracledb.AsyncConnection:
    """Resolve the same allowlisted wallet/TNS options as oracle-check."""
    import oracledb

    if not oracledb.is_thin_mode():
        raise ValueError("Oracle runtime requires native Thin mode.")
    params = _connection_params(_oracle_url(database_url), ORACLE_CONNECT_TIMEOUT_SECONDS)
    async with asyncio.timeout(ORACLE_CONNECT_TIMEOUT_SECONDS):
        connection = await oracledb.connect_async(params=params, conn_class=_owned_connection_class())
    connection.call_timeout = ORACLE_CALL_TIMEOUT_MS
    try:
        with connection.cursor() as cursor:
            await cursor.execute("ALTER SESSION SET TIME_ZONE = '+00:00'")
    except BaseException:
        await connection.close()
        raise
    return connection


def create_oracle_async_engine(database_url: str, *, pool_size: int, max_overflow: int) -> AsyncEngine:
    """Create either runtime pool within the shared Always Free session budget."""
    url = _oracle_url(database_url)
    OracleSessionBudget(pool_size=pool_size, max_overflow=max_overflow).require_capacity()

    async def _connect() -> oracledb.AsyncConnection:
        return await connect_oracle_async(database_url)

    return create_async_engine(
        # Connection secrets/options are consumed only by the native creator;
        # SQLAlchemy must not reinterpret wallet_password as a dialect flag.
        url.set(query={}),
        async_creator=_connect,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=_POOL_TIMEOUT_SECONDS,
        pool_pre_ping=True,
        pool_recycle=_POOL_RECYCLE_SECONDS,
        echo=False,
        hide_parameters=True,
    )


def create_oracle_sync_engine(database_url: str, **kwargs: Any) -> Engine:
    """Sync migration connections use the identical wallet and UTC policy."""
    url = _oracle_url(database_url)

    def _connect() -> oracledb.Connection:
        import oracledb

        params = _connection_params(url, ORACLE_CONNECT_TIMEOUT_SECONDS)
        connection = oracledb.connect(params=params)
        connection.call_timeout = ORACLE_MIGRATION_CALL_TIMEOUT_MS
        try:
            with connection.cursor() as cursor:
                cursor.execute("ALTER SESSION SET TIME_ZONE = '+00:00'")
        except BaseException:
            connection.close()
            raise
        return connection

    kwargs.setdefault("hide_parameters", True)
    return create_engine(url.set(query={}), creator=_connect, **kwargs)
