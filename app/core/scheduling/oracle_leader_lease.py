"""Oracle scheduler coordination; the application backend remains disabled."""

from __future__ import annotations

from typing import cast

from sqlalchemy import CursorResult, Float, bindparam, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

_LOCK = text("SELECT id FROM scheduler_leader WHERE id = 1 FOR UPDATE")
_INSERT = text(
    "INSERT INTO scheduler_leader (id, leader_id, acquired_at, expires_at) "
    "VALUES (1, :leader_id, SYSTIMESTAMP, SYSTIMESTAMP + NUMTODSINTERVAL(:ttl, 'SECOND'))"
).bindparams(bindparam("ttl", type_=Float))
_ACQUIRE = text(
    "UPDATE scheduler_leader SET leader_id = :leader_id, acquired_at = SYSTIMESTAMP, "
    "expires_at = SYSTIMESTAMP + NUMTODSINTERVAL(:ttl, 'SECOND') "
    "WHERE id = 1 AND (leader_id = :leader_id OR expires_at < SYSTIMESTAMP)"
).bindparams(bindparam("ttl", type_=Float))
_RENEW = text(
    "UPDATE scheduler_leader SET expires_at = SYSTIMESTAMP + NUMTODSINTERVAL(:ttl, 'SECOND') "
    "WHERE id = 1 AND leader_id = :leader_id AND expires_at > SYSTIMESTAMP"
).bindparams(bindparam("ttl", type_=Float))
_REMAINING = text(
    "SELECT EXTRACT(DAY FROM (expires_at - SYSTIMESTAMP)) * 86400 "
    "+ EXTRACT(HOUR FROM (expires_at - SYSTIMESTAMP)) * 3600 "
    "+ EXTRACT(MINUTE FROM (expires_at - SYSTIMESTAMP)) * 60 "
    "+ EXTRACT(SECOND FROM (expires_at - SYSTIMESTAMP)) "
    "FROM scheduler_leader WHERE id = 1 AND leader_id = :leader_id"
)


async def acquire_oracle_leader_lease(session: AsyncSession, *, leader_id: str, ttl: float) -> float | None:
    """Return remaining database lifetime, leaving commit to the lease owner."""
    parameters = {"leader_id": leader_id, "ttl": ttl}
    for _ in range(3):
        exists = await session.scalar(_LOCK)
        if exists is None:
            try:
                async with session.begin_nested():
                    await session.execute(_INSERT, parameters)
            except IntegrityError as exc:
                original = exc.orig
                error = original.args[0] if original is not None and original.args else None
                if getattr(error, "code", None) != 1:
                    raise
                continue
        # Evaluate the clock only after the row-lock or first-insert race has
        # completed. A timestamp in the waiting statement would be stale.
        result = await session.execute(_ACQUIRE, parameters)
        if cast(CursorResult, result).rowcount != 1:
            return None
        return await _remaining(session, leader_id)
    raise RuntimeError("Oracle scheduler lease changed repeatedly during acquisition; retry the request")


async def renew_oracle_leader_lease(session: AsyncSession, *, leader_id: str, ttl: float) -> float | None:
    """Never renew an expired lease, including after waiting behind a writer."""
    if await session.scalar(_LOCK) is None:
        return None
    result = await session.execute(_RENEW, {"leader_id": leader_id, "ttl": ttl})
    if cast(CursorResult, result).rowcount != 1:
        return None
    return await _remaining(session, leader_id)


async def _remaining(session: AsyncSession, leader_id: str) -> float:
    value = await session.scalar(_REMAINING, {"leader_id": leader_id})
    if value is None:
        raise RuntimeError("Oracle scheduler lease disappeared while its row lock was held")
    return float(value)
