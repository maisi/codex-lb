"""Pristine Oracle target checks and pre-copy identifier preparation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, DefaultClause, Sequence, create_engine, func, inspect, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import Base
from app.db.oracle_baseline import load_oracle_baseline, oracle_schema_drift
from app.db.oracle_transfer_fence import has_incomplete_transfer


class OracleTransferError(RuntimeError):
    """A sanitized transfer failure suitable for operator-facing output."""


def _normalized(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return value


def assert_pristine_target(connection: Connection) -> None:
    """Compare logical seed values with the immutable baseline, with bounded reads."""
    reference = create_engine("sqlite://")
    try:
        with reference.begin() as baseline:
            Base.metadata.create_all(baseline)
            for seed in load_oracle_baseline().seeds:
                baseline.exec_driver_sql(seed.replace(" FROM DUAL", "").replace("TIMESTAMP '", "'"))
            for table in Base.metadata.sorted_tables:
                columns = [
                    column
                    for column in table.c
                    if not (
                        column.name in {"created_at", "updated_at"}
                        and isinstance(column.type, DateTime)
                        and isinstance(column.server_default, DefaultClause)
                        and str(column.server_default.arg).upper() in {"NOW()", "CURRENT_TIMESTAMP"}
                    )
                ]
                expected = {tuple(_normalized(value) for value in row) for row in baseline.execute(select(*columns))}
                with connection.execute(select(*columns)) as result:
                    rows = result.fetchmany(len(expected) + 1)
                actual = {tuple(_normalized(value) for value in row) for row in rows}
                if len(rows) != len(expected) or actual != expected:
                    raise OracleTransferError(f"Oracle target is not a pristine baseline: {table.name}")
    except SQLAlchemyError:
        raise OracleTransferError("Could not verify pristine Oracle target contents") from None
    finally:
        reference.dispose()


def prepare_target(database_url: str, connection: Connection, *, dry_run: bool) -> None:
    """Inspect only; initialization and all mutation remain owned by the caller."""
    from app.db.migrate import inspect_migration_state

    try:
        tables = set(inspect(connection).get_table_names())
        snapshot = load_oracle_baseline()
        expected = {table.name for table in snapshot.tables}
        if not tables:
            if oracle_schema_drift(connection, snapshot, allow_missing=True):
                raise OracleTransferError("Oracle target contains incompatible existing objects")
            return
        if tables - expected - {"alembic_version"} or not expected <= tables:
            raise OracleTransferError("Oracle target must be empty or a complete pristine baseline")
        if oracle_schema_drift(connection, snapshot):
            raise OracleTransferError("Oracle target schema differs from its verified baseline")
        state = inspect_migration_state(database_url)
        if not state.has_alembic_version_table or state.needs_upgrade or state.is_ahead:
            raise OracleTransferError("Initialized Oracle target must have its own migration ledger at head")
        # An interrupted transfer's committed batches are restarted, never accepted as pristine data.
        if not has_incomplete_transfer(connection):
            assert_pristine_target(connection)
    except SQLAlchemyError:
        raise OracleTransferError("Could not inspect Oracle transfer target") from None


def lock_target_tables(connection: Connection) -> None:
    """Fence target writes for the complete data transaction without issuing DDL."""
    try:
        for table in Base.metadata.sorted_tables:
            name = connection.dialect.identifier_preparer.format_table(table)
            connection.exec_driver_sql(f"LOCK TABLE {name} IN EXCLUSIVE MODE NOWAIT")
    except SQLAlchemyError:
        raise OracleTransferError(
            "Could not lock Oracle target tables; stop every target application process"
        ) from None


def advance_sequences(source: Connection, target: Connection) -> None:
    """Advance all generated IDs before copy DML; Oracle sequence DDL commits."""
    try:
        has_sqlite_sequence = source.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sqlite_sequence'"
        ).scalar()
        for table in Base.metadata.sorted_tables:
            for column in table.c:
                if not isinstance(column.default, Sequence):
                    continue
                highwater = int(source.scalar(select(func.max(column))) or 0)
                if has_sqlite_sequence:
                    historical = source.execute(
                        text("SELECT seq FROM sqlite_sequence WHERE name = :name"), {"name": table.name}
                    ).scalar()
                    highwater = max(highwater, int(historical or 0))
                sequence = column.default
                current = target.execute(
                    text("SELECT last_number FROM user_sequences WHERE sequence_name = :name"),
                    {"name": str(sequence.name).upper()},
                ).scalar_one()
                next_value = max(highwater + 1, int(current))
                # LAST_NUMBER is a cache boundary, not the actual next value.
                # Restart even when it already exceeds the source high-water
                # mark, discarding cached values that might collide with it.
                name = target.dialect.identifier_preparer.format_sequence(sequence)
                target.exec_driver_sql(f"ALTER SEQUENCE {name} RESTART START WITH {next_value}")
    except (SQLAlchemyError, ValueError, OverflowError):
        raise OracleTransferError("Could not prepare Oracle identifier sequences before the data transaction") from None
