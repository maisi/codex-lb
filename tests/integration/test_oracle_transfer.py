"""Destructive transfer tests: the configured URL MUST own a disposable schema."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, insert, inspect, select
from sqlalchemy.engine import Engine

from app.db.migrate import current_revision, run_upgrade
from app.db.models import Account, AuditLog, Base, ModelContextWindowOverride
from app.db.oracle_baseline import load_oracle_baseline
from app.db.oracle_connection import create_oracle_sync_engine
from app.db.oracle_transfer import transfer_sqlite_to_oracle
from app.db.oracle_transfer_target import OracleTransferError

_URL = os.environ.get("CODEX_LB_TEST_ORACLE_BASELINE_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _URL, reason="Set CODEX_LB_TEST_ORACLE_BASELINE_URL to a disposable, empty schema."),
]


@pytest.fixture
def oracle_target() -> Iterator[Engine]:
    pytest.importorskip("oracledb")
    engine = create_oracle_sync_engine(_URL, hide_parameters=True)
    snapshot = load_oracle_baseline()
    expected = {table.name for table in snapshot.tables} | {"alembic_version"}

    def reset() -> None:
        with engine.begin() as connection:
            existing = set(inspect(connection).get_table_names())
            assert existing <= expected, "Refusing to reset a schema containing unrelated tables"
            for table in reversed(snapshot.tables):
                if table.name in existing:
                    connection.exec_driver_sql(f"DROP TABLE {table.name} CASCADE CONSTRAINTS PURGE")
            if "alembic_version" in existing:
                connection.exec_driver_sql("DROP TABLE alembic_version PURGE")
            sequences = set(inspect(connection).get_sequence_names())
            for sequence in snapshot.sequences:
                if sequence.name in sequences:
                    connection.exec_driver_sql(f"DROP SEQUENCE {sequence.name}")

    reset()
    try:
        yield engine
    finally:
        reset()
        engine.dispose()


def test_real_oracle_transfer_retains_values_ledger_and_sequence_highwater(
    oracle_target: Engine, tmp_path: Path
) -> None:
    source = tmp_path / "store.db"
    key_file = tmp_path / "encryption.key"
    key_file.write_bytes(Fernet.generate_key())
    encrypted = Fernet(key_file.read_bytes()).encrypt(b"original account token")
    run_upgrade(f"sqlite:///{source}", bootstrap_legacy=False)
    instant = datetime(2026, 10, 24, 12, 34, 56, 123456, tzinfo=timezone.utc)
    sqlite = create_engine(f"sqlite:///{source}")
    try:
        with sqlite.begin() as connection:
            connection.execute(
                insert(Account).values(
                    id="original",
                    email="owner@example.test",
                    plan_type="plus",
                    last_refresh=instant,
                    access_token_encrypted=encrypted,
                    refresh_token_encrypted=encrypted,
                    id_token_encrypted=encrypted,
                )
            )
            for offset, value in enumerate((None, "", "\x01", "\x01\x01", "🦊" * 6000)):
                connection.execute(
                    insert(AuditLog).values(
                        id=9000 + offset, action=f"value-{offset}", details=value, timestamp=instant
                    )
                )
            connection.execute(insert(ModelContextWindowOverride).values(slug="", context_window=1000))
        before = source.read_bytes()
        dry_run = transfer_sqlite_to_oracle(_URL, source_sqlite=source, dry_run=True, progress=lambda _: None)
        assert dry_run.needs_target_preparation is True
        with oracle_target.connect() as connection:
            assert inspect(connection).get_table_names() == []
        report = transfer_sqlite_to_oracle(_URL, source_sqlite=source, batch_size=2, progress=lambda _: None)
        assert {table.name for table in report.tables} == set(Base.metadata.tables)
        assert source.read_bytes() == before
        assert current_revision(_URL) == "20261024_000000_oracle_baseline"
        with oracle_target.begin() as connection:
            assert connection.scalar(select(Account.access_token_encrypted)) == encrypted
            assert connection.scalar(select(ModelContextWindowOverride.slug)) == ""
            for offset, value in enumerate((None, "", "\x01", "\x01\x01", "🦊" * 6000)):
                row = connection.execute(
                    select(AuditLog.details, AuditLog.timestamp).where(AuditLog.id == 9000 + offset)
                ).one()
                assert tuple(row) == (value, instant)
            result = connection.execute(insert(AuditLog).values(action="after-transfer"))
            primary_key = result.inserted_primary_key
            assert primary_key is not None and primary_key[0] > 9004
        with pytest.raises(OracleTransferError, match="pristine"):
            transfer_sqlite_to_oracle(_URL, source_sqlite=source, progress=lambda _: None)
    finally:
        sqlite.dispose()


async def test_real_oracle_interrupted_transfer_fences_startup_and_restarts(
    oracle_target: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import event
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import app.db.oracle_transfer as transfer
    from app.db.oracle_connection import create_oracle_async_engine
    from app.db.oracle_transfer_fence import (
        IncompleteOracleTransferError,
        has_incomplete_transfer,
        verify_no_incomplete_oracle_transfer,
    )

    source = tmp_path / "store.db"
    key_file = tmp_path / "encryption.key"
    key_file.write_bytes(Fernet.generate_key())
    encrypted = Fernet(key_file.read_bytes()).encrypt(b"original account token")
    run_upgrade(f"sqlite:///{source}", bootstrap_legacy=False)
    sqlite = create_engine(f"sqlite:///{source}")
    try:
        with sqlite.begin() as connection:
            connection.execute(
                insert(Account).values(
                    id="original",
                    email="owner@example.test",
                    plan_type="plus",
                    last_refresh=datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc),
                    access_token_encrypted=encrypted,
                    refresh_token_encrypted=encrypted,
                    id_token_encrypted=encrypted,
                )
            )
            for offset in range(5):
                connection.execute(insert(AuditLog).values(id=9100 + offset, action=f"row-{offset}"))
    finally:
        sqlite.dispose()

    def sabotaged_engine(url: str) -> Engine:
        engine = create_oracle_sync_engine(url)

        @event.listens_for(engine, "before_cursor_execute")
        def fail_audit_copy(_connection, _cursor, statement, *_args) -> None:
            if statement.startswith("INSERT INTO audit_logs"):
                raise RuntimeError("injected failure after earlier committed batches")

        return engine

    monkeypatch.setattr(transfer, "create_oracle_sync_engine", sabotaged_engine)
    with pytest.raises(OracleTransferError, match="incomplete"):
        transfer_sqlite_to_oracle(_URL, source_sqlite=source, batch_size=2, progress=lambda _: None)
    monkeypatch.undo()
    with oracle_target.connect() as connection:
        assert has_incomplete_transfer(connection)
        assert connection.scalar(select(Account.id)) == "original"

    async_engine = create_oracle_async_engine(_URL, pool_size=1, max_overflow=0)
    try:
        with pytest.raises(IncompleteOracleTransferError):
            await verify_no_incomplete_oracle_transfer(async_sessionmaker(async_engine), database_url=_URL)
        dry_run = transfer_sqlite_to_oracle(_URL, source_sqlite=source, dry_run=True, progress=lambda _: None)
        assert dry_run.target_incomplete_transfer is True
        report = transfer_sqlite_to_oracle(_URL, source_sqlite=source, batch_size=2, progress=lambda _: None)
        assert report.target_incomplete_transfer is True
        await verify_no_incomplete_oracle_transfer(async_sessionmaker(async_engine), database_url=_URL)
    finally:
        await async_engine.dispose()
    with oracle_target.connect() as connection:
        assert not has_incomplete_transfer(connection)
        assert connection.scalar(select(Account.access_token_encrypted)) == encrypted
        assert sorted(connection.scalars(select(AuditLog.id).where(AuditLog.id >= 9100))) == list(range(9100, 9105))
