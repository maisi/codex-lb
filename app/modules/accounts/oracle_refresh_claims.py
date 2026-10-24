"""Prepared Oracle token-refresh ownership using short row-locked transactions."""

from __future__ import annotations

import math
from typing import cast

from sqlalchemy import CursorResult, Float, bindparam, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.oracle_errors import is_oracle_unique_violation

_NOW = "SYS_EXTRACT_UTC(SYSTIMESTAMP)"
_EXPIRY = f"{_NOW} + NUMTODSINTERVAL(:ttl, 'SECOND')"
_LOCK = text("SELECT account_id FROM account_refresh_claims WHERE account_id = :account_id FOR UPDATE")
_INSERT = text(
    "INSERT INTO account_refresh_claims (account_id, claimed_by, claimed_at, claim_expires_at) "
    f"VALUES (:account_id, :claimed_by, {_NOW}, {_EXPIRY})"
).bindparams(bindparam("ttl", type_=Float))
_UPDATE = text(
    f"UPDATE account_refresh_claims SET claimed_by = :claimed_by, claimed_at = {_NOW}, claim_expires_at = {_EXPIRY} "
    f"WHERE account_id = :account_id AND (claimed_by = :claimed_by OR claim_expires_at < {_NOW})"
).bindparams(bindparam("ttl", type_=Float))


async def acquire_oracle_refresh_claim(session: AsyncSession, *, account_id: str, claimed_by: str, ttl: float) -> bool:
    if not math.isfinite(ttl) or ttl <= 0:
        raise ValueError("Oracle refresh claim TTL must be finite and positive")
    parameters = {"account_id": account_id, "claimed_by": claimed_by, "ttl": ttl}
    for _ in range(3):
        exists = await session.scalar(_LOCK, {"account_id": account_id})
        if exists is None:
            try:
                async with session.begin_nested():
                    await session.execute(_INSERT, parameters)
            except IntegrityError as exc:
                if not is_oracle_unique_violation(exc):
                    raise
                continue
        # This statement begins only after the lock or insert race completes.
        # UTC TIMESTAMP values match the existing naive-UTC storage contract.
        result = await session.execute(_UPDATE, parameters)
        return cast(CursorResult, result).rowcount == 1
    raise RuntimeError("Oracle refresh claim changed repeatedly during acquisition; retry the request")
