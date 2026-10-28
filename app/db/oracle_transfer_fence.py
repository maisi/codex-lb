"""Startup fence for an Oracle target whose batched SQLite transfer has not completed."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config.settings import get_settings
from app.db.models import RuntimeSentinel

INCOMPLETE_TRANSFER_SENTINEL = "oracle_transfer_incomplete"


class IncompleteOracleTransferError(RuntimeError):
    """Raised when the application would start on a partially transferred Oracle database."""


def has_incomplete_transfer(connection: Connection) -> bool:
    name = connection.scalar(select(RuntimeSentinel.name).where(RuntimeSentinel.name == INCOMPLETE_TRANSFER_SENTINEL))
    return name is not None


async def verify_no_incomplete_oracle_transfer(
    session_factory: Callable[[], AsyncSession] | None = None,
    *,
    database_url: str | None = None,
) -> None:
    """Refuse Oracle startup while an interrupted transfer's committed batches are present."""
    url = get_settings().database_url if database_url is None else database_url
    if not url.startswith("oracle+oracledb://"):
        return
    if session_factory is None:
        from app.db.session import SessionLocal

        make_session: Callable[[], AsyncSession] = SessionLocal
    else:
        make_session = session_factory
    async with make_session() as session:
        marker = await session.scalar(
            select(RuntimeSentinel.name).where(RuntimeSentinel.name == INCOMPLETE_TRANSFER_SENTINEL)
        )
    if marker is not None:
        raise IncompleteOracleTransferError(
            "The Oracle database holds an incomplete SQLite transfer and must not serve traffic. Keep the "
            "SQLite installation stopped and repeat `python -m app.db.migrate migrate-to-oracle`, which "
            "restarts the transfer from a cleared target."
        )
