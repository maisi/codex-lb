from __future__ import annotations

import hashlib
import shutil
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from cryptography.fernet import Fernet
from sqlalchemy import Column, Enum, create_engine, event, select, text
from sqlalchemy.engine import Connection, Engine

import app.db.migrate as migrate
import app.db.oracle_transfer as transfer
from app.db.migration_lock import migration_lock
from app.db.models import Base
from app.db.oracle_baseline import load_oracle_baseline
from app.db.oracle_transfer_target import OracleTransferError, assert_pristine_target
from app.db.sqlite_utils import acquire_sqlite_runstate_lock, release_sqlite_runstate_lock

_TARGET_URL = "oracle+oracledb://transfer:private@localhost:1521/?service_name=test"
_INSTANT = datetime(2026, 10, 24, 12, 34, 56, 123456, tzinfo=timezone.utc)
_CIPHER_KEY = b"bW1tbW1tbW1tbW1tbW1tbW1tbW1tbW1tbW1tbW1tbW0="


def _sqlite_engine(path: Path) -> Engine:
    engine = create_engine(f"sqlite:///{path}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    return engine


def _required_value(column: Column[Any]) -> Any:
    if isinstance(column.type, Enum):
        return column.type.enums[0]
    python_type = column.type.python_type
    return {str: "sample", int: 1, float: 1.25, bool: True, bytes: b"\x00\xff", datetime: _INSTANT}[python_type]


def _populate_every_table(connection: Connection, cipher: Fernet) -> None:
    """Exercise metadata coverage with real typed, foreign-key-valid rows."""
    for table in Base.metadata.sorted_tables:
        if connection.execute(select(table).limit(1)).first() is not None:
            continue
        values: dict[str, Any] = {}
        for column in table.c:
            if column.nullable or column.default is not None or column.server_default is not None:
                continue
            if column.primary_key and column.autoincrement is True:
                continue
            if column.foreign_keys:
                parent = next(iter(column.foreign_keys)).column
                values[column.name] = connection.scalar(select(parent).limit(1))
            else:
                values[column.name] = _required_value(column)
        connection.execute(table.insert().values(**values))
    for table in Base.metadata.sorted_tables:
        encrypted = {
            column.name: cipher.encrypt(b"preserved secret") for column in table.c if column.name.endswith("_encrypted")
        }
        if encrypted:
            connection.execute(table.update().values(**encrypted))
    sentinels = Base.metadata.tables["runtime_sentinels"]
    connection.execute(
        sentinels.insert().values(
            name="encryption_key_fingerprint", value="sha256:" + hashlib.sha256(_CIPHER_KEY).hexdigest()
        )
    )
    audit = Base.metadata.tables["audit_logs"]
    for offset, value in enumerate((None, "", "\x01", "🦊" * 6000)):
        connection.execute(audit.insert().values(action=f"fidelity-{offset}", details=value, timestamp=_INSTANT))
    # Both self-references form cycles and cannot be copied in insertion order.
    roles = Base.metadata.tables["dashboard_roles"]
    for role_id in ("a-child", "z-parent"):
        connection.execute(roles.insert().values(id=role_id, slug=role_id, name=role_id, kind="custom"))
    connection.execute(roles.update().where(roles.c.id == "a-child").values(cloned_from_role_id="z-parent"))
    connection.execute(roles.update().where(roles.c.id == "z-parent").values(cloned_from_role_id="a-child"))
    users = Base.metadata.tables["dashboard_users"]
    for user_id in ("a-user", "z-user"):
        connection.execute(users.insert().values(id=user_id, username=user_id, role_id="a-child"))
    connection.execute(users.update().where(users.c.id == "a-user").values(created_by_user_id="z-user"))
    connection.execute(users.update().where(users.c.id == "z-user").values(created_by_user_id="a-user"))


@pytest.fixture(scope="module")
def source_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    source = tmp_path_factory.mktemp("oracle-transfer-source") / "store.db"
    migrate.run_upgrade(f"sqlite:///{source}", bootstrap_legacy=False)
    source.with_name("encryption.key").write_bytes(_CIPHER_KEY)
    engine = _sqlite_engine(source)
    try:
        with engine.begin() as connection:
            _populate_every_table(connection, Fernet(_CIPHER_KEY))
    finally:
        engine.dispose()
    return source


@pytest.fixture
def source(source_template: Path, tmp_path: Path) -> Path:
    path = tmp_path / "store.db"
    shutil.copy2(source_template, path)
    shutil.copy2(source_template.with_name("encryption.key"), path.with_name("encryption.key"))
    return path


@pytest.fixture
def target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    engine = _sqlite_engine(tmp_path / "oracle.db")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        for seed in load_oracle_baseline().seeds:
            connection.exec_driver_sql(seed.replace(" FROM DUAL", "").replace("TIMESTAMP '", "'"))
        connection.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(255) NOT NULL)")
        connection.exec_driver_sql("INSERT INTO alembic_version VALUES ('20261024_000000_oracle_baseline')")
    real_upgrade = migrate.run_upgrade

    def upgrade(database_url: str, *args, **kwargs):
        if database_url == _TARGET_URL:
            return None
        return real_upgrade(database_url, *args, **kwargs)

    @contextmanager
    def lock(database_url: str, *, timeout_seconds: float):
        if database_url == _TARGET_URL:
            yield
        else:
            with migration_lock(database_url, timeout_seconds=timeout_seconds):
                yield

    def prepare(database_url: str, connection: Connection, *, dry_run: bool) -> None:
        del database_url, dry_run
        assert_pristine_target(connection)

    monkeypatch.setattr(transfer, "create_oracle_sync_engine", lambda _url: engine)
    monkeypatch.setattr(transfer, "migration_lock", lock)
    monkeypatch.setattr(transfer, "prepare_target", prepare)
    monkeypatch.setattr(transfer, "advance_sequences", lambda _source, _target: None)
    monkeypatch.setattr(transfer, "lock_target_tables", lambda _target: None)
    monkeypatch.setattr(migrate, "run_upgrade", upgrade)
    try:
        yield engine
    finally:
        engine.dispose()


def _contents(engine: Engine) -> dict[str, list[tuple[Any, ...]]]:
    with engine.connect() as connection:
        return {
            table.name: [tuple(row) for row in connection.execute(select(table).order_by(*table.primary_key.columns))]
            for table in Base.metadata.sorted_tables
        }


def test_public_transfer_copies_every_table_and_preserves_source(source: Path, target: Engine) -> None:
    before = source.read_bytes()
    fenced = False

    def verify_source_fence(_message: str) -> None:
        nonlocal fenced
        if not fenced:
            with sqlite3.connect(source, timeout=0) as writer, pytest.raises(sqlite3.OperationalError, match="locked"):
                writer.execute("BEGIN IMMEDIATE")
            fenced = True

    report = transfer.transfer_sqlite_to_oracle(
        _TARGET_URL, source_sqlite=source, batch_size=1, progress=verify_source_fence
    )
    source_engine = _sqlite_engine(source)
    try:
        assert _contents(target) == _contents(source_engine)
    finally:
        source_engine.dispose()
    assert source.read_bytes() == before
    assert source.with_name("encryption.key").read_bytes() == _CIPHER_KEY
    assert fenced is True
    assert {row.name for row in report.tables} == set(Base.metadata.tables)
    assert all(row.rows > 0 and len(row.checksum) == 64 for row in report.tables)
    assert report.dry_run is False
    with target.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20261024_000000_oracle_baseline"


def test_dry_run_performs_no_target_mutation(source: Path, target: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    before = _contents(target)

    def reject_write(_connection, _cursor, statement, _parameters, _context, _executemany) -> None:
        assert statement.lstrip().split()[0].upper() not in {"INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP"}

    event.listen(target, "before_cursor_execute", reject_write)
    report = transfer.transfer_sqlite_to_oracle(
        _TARGET_URL, source_sqlite=source, dry_run=True, progress=lambda _: None
    )
    assert report.dry_run is True
    assert _contents(target) == before


@pytest.mark.parametrize("key_failure", ["missing", "invalid", "wrong", "wrong_ciphertext"])
def test_key_validation_precedes_target_access(source: Path, key_failure: str, monkeypatch: pytest.MonkeyPatch) -> None:
    key = source.with_name("encryption.key")
    if key_failure == "missing":
        key.unlink()
    elif key_failure == "invalid":
        key.write_bytes(b"invalid")
    elif key_failure == "wrong":
        key.write_bytes(Fernet.generate_key())
    else:
        engine = _sqlite_engine(source)
        with engine.begin() as connection:
            connection.execute(
                Base.metadata.tables["accounts"]
                .update()
                .values(access_token_encrypted=Fernet(Fernet.generate_key()).encrypt(b"secret"))
            )
        engine.dispose()
    monkeypatch.setattr(transfer, "create_oracle_sync_engine", lambda _: pytest.fail("invalid source reached target"))
    with pytest.raises(OracleTransferError, match="key|incompatible"):
        transfer.transfer_sqlite_to_oracle(_TARGET_URL, source_sqlite=source, progress=lambda _: None)
    assert key.exists() is (key_failure != "missing")


@pytest.mark.parametrize("source_failure", ["live", "writer", "unknown_table", "ahead", "foreign_key"])
def test_unsafe_source_is_rejected_before_target_access(
    source: Path, source_failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = None
    if source_failure == "live":
        held = acquire_sqlite_runstate_lock(source)
    elif source_failure == "writer":
        held = sqlite3.connect(source)
        held.execute("BEGIN IMMEDIATE")
    else:
        with sqlite3.connect(source) as connection:
            if source_failure == "unknown_table":
                connection.execute("CREATE TABLE unrelated_operator_data (id INTEGER)")
            elif source_failure == "ahead":
                connection.execute("UPDATE alembic_version SET version_num = '20990101_future'")
            else:
                connection.execute("UPDATE api_key_accounts SET account_id = 'missing-account'")
    monkeypatch.setattr(transfer, "create_oracle_sync_engine", lambda _: pytest.fail("invalid source reached target"))
    try:
        with pytest.raises(OracleTransferError):
            transfer.transfer_sqlite_to_oracle(_TARGET_URL, source_sqlite=source, progress=lambda _: None)
    finally:
        if held is not None:
            release_sqlite_runstate_lock(held)


@pytest.mark.parametrize("failure", ["insert", "verification"])
def test_partial_transfer_rolls_back_all_rows(source: Path, target: Engine, failure: str) -> None:
    before = _contents(target)

    def sabotage(connection, _cursor, statement, _parameters, _context, _executemany) -> None:
        if statement.startswith("INSERT INTO audit_logs"):
            if failure == "insert":
                raise RuntimeError("database credential must never appear in public errors")
            connection.exec_driver_sql("UPDATE audit_logs SET details = 'corrupted'")

    event.listen(target, "after_cursor_execute", sabotage)
    with pytest.raises(OracleTransferError) as error:
        transfer.transfer_sqlite_to_oracle(_TARGET_URL, source_sqlite=source, batch_size=1, progress=lambda _: None)
    assert "credential" not in str(error.value)
    assert _contents(target) == before
    event.remove(target, "after_cursor_execute", sabotage)
    report = transfer.transfer_sqlite_to_oracle(_TARGET_URL, source_sqlite=source, progress=lambda _: None)
    assert report.dry_run is False


@pytest.mark.parametrize("used", ["application_row", "changed_seed"])
def test_used_target_is_rejected_without_overwriting(source: Path, target: Engine, used: str) -> None:
    with target.begin() as connection:
        if used == "application_row":
            connection.execute(Base.metadata.tables["audit_logs"].insert().values(action="existing installation"))
        else:
            connection.execute(Base.metadata.tables["dashboard_settings"].update().values(api_key_auth_enabled=True))
    before = _contents(target)
    with pytest.raises(OracleTransferError, match="pristine"):
        transfer.transfer_sqlite_to_oracle(_TARGET_URL, source_sqlite=source, progress=lambda _: None)
    assert _contents(target) == before


def test_pristine_guard_ignores_generated_seed_timestamps(target: Engine) -> None:
    roles = Base.metadata.tables["dashboard_roles"]
    with target.begin() as connection:
        connection.execute(roles.update().values(created_at=_INSTANT, updated_at=_INSTANT))
        assert_pristine_target(connection)


def test_cli_runs_actual_transfer(source: Path, target: Engine, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    key = source.with_name("selected.key")
    source.with_name("encryption.key").rename(key)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "codex-lb-db",
            "--db-url",
            _TARGET_URL,
            "migrate-to-oracle",
            "--source-sqlite",
            str(source),
            "--batch-size",
            "2",
            "--source-key-file",
            str(key),
        ],
    )
    migrate.main()
    assert "oracle_transfer=complete" in capsys.readouterr().out
    with target.connect() as connection:
        assert connection.scalar(select(Base.metadata.tables["accounts"].c.email)) == "sample"


def test_older_source_is_upgraded_only_in_private_snapshot(source: Path, target: Engine) -> None:
    url = f"sqlite:///{source}"
    parent = "20260929_000000_merge_upstream_post_beta9_and_fork"
    command.downgrade(migrate._build_alembic_config(url), parent)
    accounts = Base.metadata.tables["accounts"]
    assignments = Base.metadata.tables["api_key_accounts"]
    source_engine = _sqlite_engine(source)
    try:
        with source_engine.begin() as connection:
            account = dict(connection.execute(select(accounts)).mappings().one())
            connection.execute(accounts.insert().values(**{**account, "id": "second-account"}))
            assignment = dict(connection.execute(select(assignments)).mappings().one())
            connection.execute(assignments.insert().values(**{**assignment, "account_id": "second-account"}))
        before = source.read_bytes()
        transfer.transfer_sqlite_to_oracle(_TARGET_URL, source_sqlite=source, progress=lambda _: None)
        assert source.read_bytes() == before
        assert migrate.current_revision(url) == parent
        with source_engine.connect() as connection:
            assert connection.scalars(select(assignments.c.priority)).all() == [0, 0]
        with target.connect() as connection:
            assert sorted(connection.scalars(select(assignments.c.priority)).all()) == [0, 1]
    finally:
        source_engine.dispose()


@pytest.mark.parametrize("batch_size", [0, -1, 10_001, True])
def test_batch_size_must_be_bounded(source: Path, batch_size: int) -> None:
    with pytest.raises(OracleTransferError, match="batch_size"):
        transfer.transfer_sqlite_to_oracle(_TARGET_URL, source_sqlite=source, batch_size=batch_size)


@pytest.mark.parametrize("incompatible", ["identifier", "raw_hash"])
def test_oracle_storage_bounds_fail_before_target_access(
    source: Path, incompatible: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _sqlite_engine(source)
    try:
        with engine.begin() as connection:
            if incompatible == "identifier":
                table = Base.metadata.tables["model_context_window_overrides"]
                connection.execute(table.update().values(slug="x" * 1025))
            else:
                table = Base.metadata.tables["dashboard_user_invites"]
                connection.execute(table.update().values(token_hash=b"x" * 33))
    finally:
        engine.dispose()
    monkeypatch.setattr(transfer, "create_oracle_sync_engine", lambda _: pytest.fail("invalid source reached target"))
    with pytest.raises(OracleTransferError, match="incompatible"):
        transfer.transfer_sqlite_to_oracle(_TARGET_URL, source_sqlite=source, progress=lambda _: None)


def test_digest_accepts_different_backend_row_order(source: Path, target: Engine) -> None:
    with target.connect() as connection:
        connection.exec_driver_sql("PRAGMA reverse_unordered_selects=ON")
    report = transfer.transfer_sqlite_to_oracle(_TARGET_URL, source_sqlite=source, progress=lambda _: None)
    assert report.dry_run is False
