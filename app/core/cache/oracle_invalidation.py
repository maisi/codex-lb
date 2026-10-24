"""Atomic version bumps for the prepared, runtime-disabled Oracle backend."""

from __future__ import annotations

from typing import cast

from sqlalchemy import CursorResult, bindparam, insert, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CacheInvalidation
from app.db.oracle_errors import is_oracle_unique_violation

_UPDATE = (
    update(CacheInvalidation)
    .where(CacheInvalidation.namespace == bindparam("namespace_key"))
    .values(version=CacheInvalidation.version + 1)
)
_INSERT = insert(CacheInvalidation).values(namespace=bindparam("namespace"), version=1)


async def bump_oracle_invalidation(session: AsyncSession, namespace: str) -> None:
    """Leave the short transaction's commit/rollback to the calling poller."""
    for _ in range(3):
        result = await session.execute(_UPDATE, {"namespace_key": namespace})
        if cast(CursorResult, result).rowcount == 1:
            return
        try:
            async with session.begin_nested():
                await session.execute(_INSERT, {"namespace": namespace})
            return
        except IntegrityError as exc:
            if not is_oracle_unique_violation(exc):
                raise
            # A simultaneous first insert won. Its committed version must be
            # incremented rather than treating the unique race as a lost bump.
    raise RuntimeError("Oracle invalidation namespace changed repeatedly; retry the bump")
