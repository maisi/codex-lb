"""Offline, verified transfer of every application table from SQLite to Oracle."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import ExitStack, closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import (
    Column,
    ColumnElement,
    LargeBinary,
    Table,
    and_,
    bindparam,
    create_engine,
    delete,
    insert,
    inspect,
    or_,
    select,
    true,
    update,
)
from sqlalchemy.dialects import oracle
from sqlalchemy.engine import Connection, Engine

from app.core.config.settings import get_settings
from app.db.migration_lock import migration_lock
from app.db.models import Base, RuntimeSentinel
from app.db.oracle_connection import create_oracle_sync_engine
from app.db.oracle_preflight import _oracle_url
from app.db.oracle_transfer_fence import INCOMPLETE_TRANSFER_SENTINEL, has_incomplete_transfer
from app.db.oracle_transfer_target import (
    OracleTransferError,
    advance_sequences,
    assert_pristine_target,
    lock_target_tables,
    prepare_target,
)
from app.db.sqlite_utils import (
    SqliteRunStateLockError,
    acquire_sqlite_runstate_lock,
    release_sqlite_runstate_lock,
)


@dataclass(frozen=True)
class TableTransferReport:
    name: str
    rows: int
    checksum: str


@dataclass(frozen=True)
class OracleTransferReport:
    tables: tuple[TableTransferReport, ...]
    dry_run: bool
    needs_target_preparation: bool
    target_incomplete_transfer: bool


def _canonical(value: Any) -> Any:
    # Explicit type boundaries distinguish NULL, empty strings, bytes and numbers.
    if value is None:
        return ["null"]
    if isinstance(value, Enum):
        return _canonical(value.value)
    if isinstance(value, datetime):
        instant = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return ["datetime", instant.isoformat(timespec="microseconds")]
    if isinstance(value, bytes):
        return ["bytes", value.hex()]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, int):
        return ["int", str(value)]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise OracleTransferError("Source contains a non-finite numeric value.")
        return ["float", (value if value else 0.0).hex()]
    if isinstance(value, str):
        return ["str", value]
    raise OracleTransferError("Source contains an unsupported value type.")


def _table_report(
    connection: Connection,
    table: Table,
    batch_size: int,
    *,
    cipher: Fernet | None = None,
) -> TableTransferReport:
    dialect = oracle.dialect()
    processors = {column.name: column.type.dialect_impl(dialect).bind_processor(dialect) for column in table.columns}
    binary_limits = {
        column.name: storage.length
        for column in table.columns
        if isinstance(storage := column.type.dialect_impl(dialect), (LargeBinary, oracle.RAW))
        and storage.length is not None
    }
    count = total = 0
    with connection.execute(select(table).where(_transferable(table))) as result:
        for batch in result.mappings().partitions(batch_size):
            for row in batch:
                if cipher is not None:
                    for column in table.columns:
                        value = row[column.name]
                        try:
                            processor = processors[column.name]
                            if processor is not None:
                                processor(value)
                            if value is not None and column.name in binary_limits:
                                if len(value) > binary_limits[column.name]:
                                    raise ValueError("Binary storage bound exceeded")
                            if value is not None and column.name.endswith("_encrypted"):
                                cipher.decrypt(value)
                        except (InvalidToken, ValueError, TypeError, OverflowError):
                            raise OracleTransferError(
                                f"Source value or encryption key is incompatible at {table.name}.{column.name}."
                            ) from None
                payload = json.dumps([_canonical(row[column.name]) for column in table.columns], ensure_ascii=True)
                total = (total + int.from_bytes(hashlib.sha256(payload.encode()).digest())) % (1 << 256)
                count += 1
    # Summing row hashes is independent of each backend's storage/collation order.
    checksum = hashlib.sha256(f"{count}:{total:064x}".encode()).hexdigest()
    return TableTransferReport(table.name, count, checksum)


@contextmanager
def _source_snapshot(source: Path) -> Iterator[str]:
    if not source.is_file():
        raise OracleTransferError("Source SQLite database does not exist or is not a regular file.")
    try:
        lifetime_lock = acquire_sqlite_runstate_lock(source)
    except SqliteRunStateLockError:
        raise OracleTransferError("Stop every process using the source SQLite installation before transfer.") from None
    try:
        with ExitStack() as locks:
            try:
                locks.enter_context(migration_lock(f"sqlite:///{source}", timeout_seconds=1))
            except TimeoutError:
                raise OracleTransferError(
                    "Stop every process using the source SQLite installation before transfer."
                ) from None
            with closing(sqlite3.connect(source.as_uri() + "?mode=rw", uri=True, timeout=0)) as fence:
                try:
                    fence.execute("BEGIN IMMEDIATE")
                except sqlite3.OperationalError:
                    raise OracleTransferError(
                        "Stop every process using the source SQLite installation before transfer."
                    ) from None
                try:
                    with TemporaryDirectory(prefix="codex-lb-oracle-transfer-") as directory:
                        snapshot = Path(directory) / "source.db"
                        with (
                            closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as reader,
                            closing(sqlite3.connect(snapshot)) as copy,
                        ):
                            reader.backup(copy)
                        snapshot.chmod(0o600)
                        yield f"sqlite:///{snapshot}"
                finally:
                    fence.rollback()
    finally:
        release_sqlite_runstate_lock(lifetime_lock)


def _prepare_source(snapshot_url: str) -> Engine:
    # Keep CLI imports lazy: migrate.main imports this module only for this command.
    from app.db.migrate import check_schema_drift, run_upgrade

    engine = create_engine(snapshot_url, hide_parameters=True)
    try:
        with engine.connect() as connection:
            if connection.exec_driver_sql("PRAGMA integrity_check").scalars().all() != ["ok"]:
                raise OracleTransferError("Source SQLite integrity check failed.")
            if "accounts" not in inspect(connection).get_table_names():
                raise OracleTransferError("Source is not an initialized codex-lb database.")
            if connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
                raise OracleTransferError("Source SQLite foreign-key check failed.")
        run_upgrade(snapshot_url, bootstrap_legacy=True)
        if check_schema_drift(snapshot_url):
            raise OracleTransferError("Source schema has unknown tables or incompatible columns.")
        with engine.connect() as connection:
            if connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
                raise OracleTransferError("Source SQLite foreign-key check failed.")
        return engine
    except BaseException:
        engine.dispose()
        raise


def _read_key(key_file: Path) -> tuple[Fernet, str]:
    try:
        key = key_file.read_bytes()
        return Fernet(key), "sha256:" + hashlib.sha256(key).hexdigest()
    except (OSError, ValueError):
        raise OracleTransferError("An existing valid source encryption.key is required; no key was created.") from None


def _check_key_fingerprint(connection: Connection, fingerprint: str) -> None:
    sentinels = Base.metadata.tables["runtime_sentinels"]
    stored = connection.scalar(select(sentinels.c.value).where(sentinels.c.name == "encryption_key_fingerprint"))
    if stored is not None and stored != fingerprint:
        raise OracleTransferError("The selected encryption key does not match the source key fingerprint.")


def _transferable(table: Table) -> ColumnElement[bool]:
    # The fence marker belongs to the target's transfer state, never to copied data.
    if table.name == RuntimeSentinel.__tablename__:
        return table.c.name != INCOMPLETE_TRANSFER_SENTINEL
    return true()


def _self_columns(table: Table) -> tuple[Column[Any], ...]:
    return tuple(column for column in table.columns if any(fk.column.table is table for fk in column.foreign_keys))


def _clear_in_batches(
    target: Connection,
    table: Table,
    condition: ColumnElement[bool],
    batch_size: int,
    *,
    values: dict[str, None] | None = None,
) -> None:
    """Delete (or null ``values`` in) matching rows, committing each primary-key batch."""
    primary_key = tuple(table.primary_key.columns)
    match = and_(*(column == bindparam(f"transfer_pk_{column.name}") for column in primary_key))
    statement = delete(table).where(match) if values is None else update(table).where(match).values(values)
    query = select(*primary_key).where(condition).limit(batch_size)
    while keys := target.execute(query).all():
        target.execute(
            statement,
            [{f"transfer_pk_{column.name}": key[index] for index, column in enumerate(primary_key)} for key in keys],
        )
        target.commit()


def _copy_table(source: Connection, target: Connection, table: Table, batch_size: int) -> None:
    self_columns = _self_columns(table)
    if any(not column.nullable for column in self_columns):
        raise OracleTransferError(f"Cannot safely transfer non-nullable self references in {table.name}.")
    with source.execute(select(table).where(_transferable(table))) as result:
        for batch in result.mappings().partitions(batch_size):
            values = [dict(row) for row in batch]
            for row in values:
                for column in self_columns:
                    row[column.name] = None
            target.execute(table.insert(), values)
            # One committed transaction per batch bounds Oracle undo by batch_size.
            target.commit()
    if not self_columns:
        return
    primary_key = tuple(table.primary_key.columns)
    restore_columns = (*self_columns, *(column for column in table.columns if column.onupdate is not None))
    statement = (
        update(table)
        .where(and_(*(column == bindparam(f"transfer_pk_{column.name}") for column in primary_key)))
        .values({column.name: bindparam(f"transfer_fk_{column.name}") for column in restore_columns})
    )
    with source.execute(select(*primary_key, *restore_columns)) as result:
        for batch in result.mappings().partitions(batch_size):
            target.execute(
                statement,
                [
                    {
                        **{f"transfer_pk_{col.name}": row[col.name] for col in primary_key},
                        **{f"transfer_fk_{col.name}": row[col.name] for col in restore_columns},
                    }
                    for row in batch
                ],
            )
            target.commit()


def _transfer_rows(
    source: Connection,
    target: Connection,
    reports: tuple[TableTransferReport, ...],
    batch_size: int,
    progress: Callable[[str], None],
) -> None:
    tables = tuple(Base.metadata.sorted_tables)
    # Clears baseline seeds, or every committed batch of an interrupted attempt.
    # Self-references are broken first so reverse-dependency deletes succeed.
    for table in reversed(tables):
        if self_columns := _self_columns(table):
            referencing = or_(*(column.is_not(None) for column in self_columns))
            _clear_in_batches(
                target, table, referencing, batch_size, values={column.name: None for column in self_columns}
            )
        _clear_in_batches(target, table, _transferable(table), batch_size)
    for table, expected in zip(tables, reports, strict=True):
        _copy_table(source, target, table, batch_size)
        actual = _table_report(target, table, batch_size)
        if actual != expected:
            raise OracleTransferError(f"Complete row verification failed for {table.name}; transfer rolled back.")
        progress(f"verified table={table.name} rows={actual.rows}")


_FENCED_FAILURE = (
    "Oracle transfer is incomplete: committed batches remain and application startup is refused until a "
    "transfer completes. Keep the SQLite source stopped and repeat migrate-to-oracle; it restarts from a "
    "cleared target. The SQLite source remains authoritative."
)


def _fence_target(target: Connection) -> None:
    """Commit the startup fence in the transaction that proved no other writer and a usable target."""
    lock_target_tables(target)
    if not has_incomplete_transfer(target):
        assert_pristine_target(target)
        target.execute(insert(RuntimeSentinel).values(name=INCOMPLETE_TRANSFER_SENTINEL, value="migrate-to-oracle"))
    target.commit()


def transfer_sqlite_to_oracle(
    database_url: str,
    *,
    source_sqlite: Path,
    source_key_file: Path | None = None,
    batch_size: int = 500,
    dry_run: bool = False,
    progress: Callable[[str], None] = print,
) -> OracleTransferReport:
    """Transfer an offline source; never replay an uncertain commit or expose driver values."""
    from app.db.migrate import run_upgrade

    _oracle_url(database_url)
    if type(batch_size) is not int or not 1 <= batch_size <= 10_000:
        raise OracleTransferError("batch_size must be between 1 and 10000.")
    source_path = source_sqlite.expanduser().resolve()
    cipher, fingerprint = _read_key((source_key_file or source_path.with_name("encryption.key")).expanduser())
    try:
        with _source_snapshot(source_path) as snapshot_url:
            source_engine = _prepare_source(snapshot_url)
            try:
                with source_engine.connect() as source:
                    _check_key_fingerprint(source, fingerprint)
                    reports = tuple(
                        _table_report(source, table, batch_size, cipher=cipher) for table in Base.metadata.sorted_tables
                    )
                    for report in reports:
                        progress(f"source table={report.name} rows={report.rows}")
                    target_engine = create_oracle_sync_engine(database_url)
                    lock_timeout = get_settings().database_migration_lock_timeout_seconds
                    try:
                        with migration_lock(database_url, timeout_seconds=lock_timeout):
                            with target_engine.connect() as target:
                                needs_preparation = not inspect(target).get_table_names()
                                prepare_target(database_url, target, dry_run=dry_run)
                                incomplete = not needs_preparation and has_incomplete_transfer(target)
                        if dry_run:
                            return OracleTransferReport(reports, True, needs_preparation, incomplete)
                        run_upgrade(database_url, bootstrap_legacy=False)
                        with migration_lock(database_url, timeout_seconds=lock_timeout):
                            with target_engine.connect() as target:
                                prepare_target(database_url, target, dry_run=False)
                                advance_sequences(source, target)
                                target.commit()
                                _fence_target(target)
                                try:
                                    _transfer_rows(source, target, reports, batch_size, progress)
                                    target.execute(
                                        delete(RuntimeSentinel).where(
                                            RuntimeSentinel.name == INCOMPLETE_TRANSFER_SENTINEL
                                        )
                                    )
                                    target.commit()
                                except Exception as exc:
                                    detail = f"{exc} " if isinstance(exc, OracleTransferError) else ""
                                    raise OracleTransferError(detail + _FENCED_FAILURE) from None
                        return OracleTransferReport(reports, False, needs_preparation, incomplete)
                    finally:
                        target_engine.dispose()
            finally:
                source_engine.dispose()
    except OracleTransferError:
        raise
    except Exception:
        raise OracleTransferError(
            "Oracle transfer failed; no success is confirmed. Pre-commit data changes are rolled back, "
            "but prepared schema and sequence gaps may remain. If commit was interrupted, inspect the target "
            "before retrying. No automatic retry was attempted."
        ) from None
