from __future__ import annotations

from collections.abc import Collection
from typing import cast

from sqlalchemy import CursorResult, Integer, bindparam, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import TextClause

from app.db.session import sqlite_writer_section

_TABLE = "file_account_pins"

# Ownership TTLs stay entirely in the database clock domain. PostgreSQL's
# clock_timestamp() is evaluated when each clause executes. A successful claim
# is followed by a guarded refresh in the same transaction so even an INSERT
# that waited behind an ultimately rolled-back unique contender receives its
# full TTL after the wait. SQLite's padded strftime form matches SQLAlchemy
# DateTime's six-digit fractional width, preserving exact lexicographic expiry
# checks.
_POSTGRES_NOW = "clock_timestamp()"
_POSTGRES_NOW_PLUS_TTL = "clock_timestamp() + make_interval(secs => :ttl)"
_POSTGRES_STATEMENT_NOW = "statement_timestamp()"
_SQLITE_NOW = "(strftime('%Y-%m-%d %H:%M:%f', 'now') || '000')"
_SQLITE_NOW_PLUS_TTL = "(strftime('%Y-%m-%d %H:%M:%f', 'now', '+' || :ttl || ' seconds') || '000')"

_POSTGRES_CLAIM = text(
    f"""
    INSERT INTO {_TABLE} (file_id, account_id, expires_at)
    VALUES (:file_id, :account_id, {_POSTGRES_NOW_PLUS_TTL})
    ON CONFLICT (file_id) DO UPDATE SET
        account_id = excluded.account_id,
        expires_at = {_POSTGRES_NOW_PLUS_TTL}
    WHERE {_TABLE}.account_id = :account_id
       OR {_TABLE}.expires_at <= {_POSTGRES_NOW}
    RETURNING account_id
    """
).bindparams(bindparam("ttl", type_=Integer))

_SQLITE_CLAIM = text(
    f"""
    INSERT INTO {_TABLE} (file_id, account_id, expires_at)
    VALUES (:file_id, :account_id, {_SQLITE_NOW_PLUS_TTL})
    ON CONFLICT (file_id) DO UPDATE SET
        account_id = excluded.account_id,
        expires_at = {_SQLITE_NOW_PLUS_TTL}
    WHERE {_TABLE}.account_id = :account_id
       OR {_TABLE}.expires_at <= {_SQLITE_NOW}
    RETURNING account_id
    """
).bindparams(bindparam("ttl", type_=Integer))

_POSTGRES_CLEANUP = text(f"DELETE FROM {_TABLE} WHERE expires_at <= {_POSTGRES_STATEMENT_NOW}")
_SQLITE_CLEANUP = text(f"DELETE FROM {_TABLE} WHERE expires_at <= {_SQLITE_NOW}")
_ORACLE_CLEANUP = text(f"DELETE FROM {_TABLE} WHERE expires_at <= SYSTIMESTAMP")

_ORACLE_LOCK_OWNER = text(f"SELECT account_id FROM {_TABLE} WHERE file_id = :file_id FOR UPDATE")
_ORACLE_INSERT = text(
    f"INSERT INTO {_TABLE} (file_id, account_id, expires_at) "
    "VALUES (:file_id, :account_id, SYSTIMESTAMP + NUMTODSINTERVAL(:ttl, 'SECOND'))"
).bindparams(bindparam("ttl", type_=Integer))
_ORACLE_UPDATE_OWNER = text(
    f"UPDATE {_TABLE} SET account_id = :account_id, "
    "expires_at = SYSTIMESTAMP + NUMTODSINTERVAL(:ttl, 'SECOND') "
    "WHERE file_id = :file_id AND (account_id = :account_id OR expires_at <= SYSTIMESTAMP)"
).bindparams(bindparam("ttl", type_=Integer))

_POSTGRES_REFRESH = text(
    f"""
    UPDATE {_TABLE}
    SET expires_at = {_POSTGRES_NOW_PLUS_TTL}
    WHERE file_id = :file_id
      AND account_id = :account_id
    RETURNING account_id
    """
).bindparams(bindparam("ttl", type_=Integer))
_SQLITE_REFRESH = text(
    f"""
    UPDATE {_TABLE}
    SET expires_at = {_SQLITE_NOW_PLUS_TTL}
    WHERE file_id = :file_id
      AND account_id = :account_id
    RETURNING account_id
    """
).bindparams(bindparam("ttl", type_=Integer))

_POSTGRES_GET_LIVE = text(f"SELECT account_id FROM {_TABLE} WHERE file_id = :file_id AND expires_at > {_POSTGRES_NOW}")
_SQLITE_GET_LIVE = text(f"SELECT account_id FROM {_TABLE} WHERE file_id = :file_id AND expires_at > {_SQLITE_NOW}")
_ORACLE_GET_LIVE = text(f"SELECT account_id FROM {_TABLE} WHERE file_id = :file_id AND expires_at > SYSTIMESTAMP")
_ORACLE_GET_LIVE_MANY = text(
    f"SELECT file_id, account_id FROM {_TABLE} WHERE file_id IN :file_ids AND expires_at > SYSTIMESTAMP"
).bindparams(bindparam("file_ids", expanding=True))

_POSTGRES_GET_LIVE_MANY = text(
    f"""
    SELECT file_id, account_id
    FROM {_TABLE}
    WHERE file_id IN :file_ids
      AND expires_at > {_POSTGRES_NOW}
    """
).bindparams(bindparam("file_ids", expanding=True))
_SQLITE_GET_LIVE_MANY = text(
    f"""
    SELECT file_id, account_id
    FROM {_TABLE}
    WHERE file_id IN :file_ids
      AND expires_at > {_SQLITE_NOW}
    """
).bindparams(bindparam("file_ids", expanding=True))

_GET_ACCOUNT = text(f"SELECT account_id FROM {_TABLE} WHERE file_id = :file_id")


class FileAccountPinOwnershipConflict(RuntimeError):
    def __init__(self, file_id: str, persisted_account_id: str, requested_account_id: str) -> None:
        super().__init__(
            f"Live file ownership conflict for {file_id!r}: "
            f"persisted={persisted_account_id!r} requested={requested_account_id!r}"
        )
        self.file_id = file_id
        self.persisted_account_id = persisted_account_id
        self.requested_account_id = requested_account_id


def build_file_account_pin_claim(*, dialect_name: str) -> TextClause:
    if dialect_name == "postgresql":
        return _POSTGRES_CLAIM
    if dialect_name == "sqlite":
        return _SQLITE_CLAIM
    raise RuntimeError(f"Unsupported database dialect for file account pins: {dialect_name}")


def build_file_account_pin_cleanup(*, dialect_name: str) -> TextClause:
    if dialect_name == "oracle":
        return _ORACLE_CLEANUP
    if dialect_name == "postgresql":
        return _POSTGRES_CLEANUP
    if dialect_name == "sqlite":
        return _SQLITE_CLEANUP
    raise RuntimeError(f"Unsupported database dialect for file account pins: {dialect_name}")


def build_file_account_pin_refresh(*, dialect_name: str) -> TextClause:
    if dialect_name == "postgresql":
        return _POSTGRES_REFRESH
    if dialect_name == "sqlite":
        return _SQLITE_REFRESH
    raise RuntimeError(f"Unsupported database dialect for file account pins: {dialect_name}")


def build_file_account_pin_live_lookup(*, dialect_name: str, many: bool = False) -> TextClause:
    if dialect_name == "oracle":
        return _ORACLE_GET_LIVE_MANY if many else _ORACLE_GET_LIVE
    if dialect_name == "postgresql":
        return _POSTGRES_GET_LIVE_MANY if many else _POSTGRES_GET_LIVE
    if dialect_name == "sqlite":
        return _SQLITE_GET_LIVE_MANY if many else _SQLITE_GET_LIVE
    raise RuntimeError(f"Unsupported database dialect for file account pins: {dialect_name}")


class FileAccountPinRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(self, file_id: str, account_id: str, *, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("File account pin TTL must be positive")
        dialect_name = self._dialect_name()
        if dialect_name == "oracle":
            await self._claim_oracle(file_id, account_id, ttl_seconds=ttl_seconds)
            return
        params = {
            "file_id": file_id,
            "account_id": account_id,
            "ttl": ttl_seconds,
        }
        async with sqlite_writer_section():
            await self._session.execute(build_file_account_pin_cleanup(dialect_name=dialect_name))
            persisted_account_id = (
                await self._session.execute(
                    build_file_account_pin_claim(dialect_name=dialect_name),
                    params,
                )
            ).scalar_one_or_none()
            if persisted_account_id is None:
                persisted_account_id = await self._session.scalar(
                    _GET_ACCOUNT,
                    {"file_id": file_id},
                )
            if persisted_account_id != account_id:
                await self._session.rollback()
                raise FileAccountPinOwnershipConflict(
                    file_id,
                    persisted_account_id or "<missing>",
                    account_id,
                )
            refreshed_account_id = (
                await self._session.execute(
                    build_file_account_pin_refresh(dialect_name=dialect_name),
                    params,
                )
            ).scalar_one_or_none()
            if refreshed_account_id != account_id:
                await self._session.rollback()
                raise RuntimeError(f"Failed to refresh file account pin after claim: {file_id!r}")
            await self._session.commit()

    async def _claim_oracle(self, file_id: str, account_id: str, *, ttl_seconds: int) -> None:
        params = {"file_id": file_id, "account_id": account_id, "ttl": ttl_seconds}
        try:
            await self._session.execute(_ORACLE_CLEANUP)
            for _ in range(3):
                persisted_account_id = await self._session.scalar(_ORACLE_LOCK_OWNER, {"file_id": file_id})
                if persisted_account_id is None:
                    try:
                        # A simultaneous first insert may win after our absent
                        # read. Recover only its unique-key race and retry the
                        # locked read; every other integrity failure propagates.
                        async with self._session.begin_nested():
                            await self._session.execute(_ORACLE_INSERT, params)
                    except IntegrityError as exc:
                        original = exc.orig
                        error = original.args[0] if original is not None and original.args else None
                        if getattr(error, "code", None) != 1:
                            raise
                        continue
                    persisted_account_id = account_id

                # This fresh statement runs AFTER the row lock/unique-key wait,
                # so expiry cannot be based on a timestamp captured before it.
                result = await self._session.execute(_ORACLE_UPDATE_OWNER, params)
                if cast(CursorResult, result).rowcount != 1:
                    raise FileAccountPinOwnershipConflict(file_id, persisted_account_id, account_id)
                await self._session.commit()
                return
            raise RuntimeError("Oracle file pin changed repeatedly during claim; retry the request")
        except BaseException:
            await self._session.rollback()
            raise

    async def get_live_account_id(self, file_id: str) -> str | None:
        return await self._session.scalar(
            build_file_account_pin_live_lookup(dialect_name=self._dialect_name()),
            {"file_id": file_id},
        )

    async def get_live_account_ids(self, file_ids: Collection[str]) -> dict[str, str]:
        unique_file_ids = tuple(dict.fromkeys(file_ids))
        if not unique_file_ids:
            return {}
        rows = (
            (
                await self._session.execute(
                    build_file_account_pin_live_lookup(
                        dialect_name=self._dialect_name(),
                        many=True,
                    ),
                    {"file_ids": unique_file_ids},
                )
            )
            .tuples()
            .all()
        )
        return dict(rows)

    def _dialect_name(self) -> str:
        return self._session.get_bind().dialect.name
