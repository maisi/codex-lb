from __future__ import annotations

from collections.abc import Collection
from hashlib import sha256
from typing import Protocol, TypedDict, cast

from sqlalchemy import Integer, outparam, text
from sqlalchemy.ext.asyncio import AsyncSession

_POSTGRES_ACCOUNT_IDENTITY_LOCK_TIMEOUT_MS = 30_000
_ORACLE_ACCOUNT_IDENTITY_LOCK = text(
    "BEGIN :result := DBMS_LOCK.REQUEST(id => :lock_id, lockmode => DBMS_LOCK.X_MODE, "
    "timeout => :timeout, release_on_commit => TRUE); END;"
).bindparams(outparam("result", Integer()))


class _OracleLockParameters(TypedDict):
    result: int


class _OracleLockResult(Protocol):
    out_parameters: _OracleLockParameters


def advisory_lock_key(scope: str, value: str) -> int:
    digest = sha256(f"{scope}:{value}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def account_identity_lock_key(chatgpt_account_id: str) -> int:
    """Return the existing PostgreSQL lock namespace for one upstream identity."""
    return advisory_lock_key("account-id", f"chatgpt:{chatgpt_account_id}")


async def lock_postgresql_account_identities(
    session: AsyncSession,
    chatgpt_account_ids: Collection[str | None],
) -> tuple[int, ...]:
    """Lock upstream identity membership in canonical transaction-scoped order."""
    bind = session.get_bind()
    if bind is None or bind.dialect.name not in {"postgresql", "oracle"}:
        return ()
    lock_keys = tuple(
        sorted(
            {
                account_identity_lock_key(chatgpt_account_id)
                for chatgpt_account_id in chatgpt_account_ids
                if chatgpt_account_id
            }
        )
    )
    if bind.dialect.name == "oracle":
        # Hash collisions only serialize unrelated identities. Use canonical
        # order after folding into Oracle's numeric user-lock namespace.
        oracle_keys = tuple(sorted({key % (1 << 30) for key in lock_keys}))
        try:
            for lock_key in oracle_keys:
                result = await session.execute(
                    _ORACLE_ACCOUNT_IDENTITY_LOCK,
                    {"lock_id": lock_key, "timeout": _POSTGRES_ACCOUNT_IDENTITY_LOCK_TIMEOUT_MS // 1000},
                )
                code = cast(_OracleLockResult, result).out_parameters["result"]
                if code == 1:
                    raise TimeoutError("Timed out waiting for Oracle account identity ownership")
                if code not in {0, 4}:
                    raise RuntimeError(f"Oracle account identity lock failed (DBMS_LOCK result {code})")
        except BaseException:
            await session.rollback()
            raise
        return lock_keys
    try:
        if lock_keys:
            # Match the database layer's existing 30-second contention budget.
            # Transaction-local scope bounds every subsequent lock in this unit
            # of work and PostgreSQL restores it at transaction end.
            await session.execute(
                text("SELECT set_config('lock_timeout', :timeout, true)"),
                {"timeout": f"{_POSTGRES_ACCOUNT_IDENTITY_LOCK_TIMEOUT_MS}ms"},
            )
        for lock_key in lock_keys:
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": lock_key},
            )
    except BaseException:
        await session.rollback()
        raise
    return lock_keys
