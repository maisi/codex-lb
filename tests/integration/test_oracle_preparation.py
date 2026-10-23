"""Opt-in tests on an owned Oracle schema; never point this at production."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import Column, Integer, MetaData, Sequence, Table, Text, create_engine, func, insert, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.oracle_schema import OracleSchemaBlockerKind, inspect_oracle_schema
from app.db.oracle_types import database_datetime, sha256_binary

_ORACLE_URL = os.environ.get("CODEX_LB_TEST_ORACLE_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _ORACLE_URL, reason="Set CODEX_LB_TEST_ORACLE_URL to an owned Oracle test schema."),
]


@pytest.fixture
def oracle_probe() -> Iterator[tuple[Engine, Table]]:
    pytest.importorskip("oracledb")
    assert make_url(_ORACLE_URL).drivername == "oracle+oracledb"
    engine = create_engine(_ORACLE_URL, pool_pre_ping=True, hide_parameters=True)
    metadata = MetaData()
    name = f"codex_probe_{uuid4().hex[:12]}"
    table = Table(
        name,
        metadata,
        Column("id", Integer, Sequence(f"{name}_seq", optional=True), primary_key=True),
        Column("recorded_at", database_datetime(), nullable=False),
        Column("expires_at", database_datetime(timezone=True), nullable=False),
        Column("created_at", database_datetime(timezone=True), nullable=False, server_default=func.current_timestamp()),
        Column("token_hash", sha256_binary(), nullable=False, unique=True),
    )
    try:
        metadata.create_all(engine)
        yield engine, table
    finally:
        try:
            metadata.drop_all(engine)
        finally:
            engine.dispose()


def _run_database_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    # Credentials stay out of process arguments and captured output is checked
    # before a test can include it in an assertion message.
    environment = {**os.environ, "CODEX_LB_DATABASE_URL": _ORACLE_URL}
    result = subprocess.run(
        [sys.executable, "-m", "app.db.migrate", *arguments],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    password = make_url(_ORACLE_URL).password
    if password and (password in result.stdout or password in result.stderr):
        pytest.fail("Database CLI exposed a credential; captured output has been withheld.")
    return result


@pytest.mark.parametrize("offset_hours", [0, 5.5, -7])
def test_oracle_types_round_trip_generated_ids_precision_and_hashes(
    oracle_probe: tuple[Engine, Table], offset_hours: float
) -> None:
    engine, table = oracle_probe
    recorded_at = datetime(2026, 10, 23, 12, 34, 56, 123456)
    expires_at = recorded_at.replace(tzinfo=timezone(timedelta(hours=offset_hours)))
    with engine.begin() as connection:
        connection.execute(text("ALTER SESSION SET TIME_ZONE = '-04:00'"))
        before = connection.scalar(select(func.sys_extract_utc(func.current_timestamp())))
        result = connection.execute(
            insert(table).values(recorded_at=recorded_at, expires_at=expires_at, token_hash=b"a" * 32)
        )
        first_key = result.inserted_primary_key
        assert first_key is not None
        first_id = first_key[0]
        result = connection.execute(
            insert(table).values(recorded_at=recorded_at, expires_at=expires_at, token_hash=b"b" * 32)
        )
        second_key = result.inserted_primary_key
        assert second_key is not None
        assert second_key[0] > first_id
        row = connection.execute(select(table).where(table.c.token_hash == b"a" * 32)).one()
        assert row.id == first_id
        assert row.recorded_at == recorded_at
        assert row.expires_at == expires_at
        assert row.expires_at.tzinfo == timezone.utc
        after = connection.scalar(select(func.sys_extract_utc(func.current_timestamp())))
        assert before <= row.created_at.replace(tzinfo=None) <= after
        assert row.created_at.tzinfo == timezone.utc
        assert row.token_hash == b"a" * 32


async def test_oracle_native_async_sqlalchemy_round_trip(oracle_probe: tuple[Engine, Table]) -> None:
    _, table = oracle_probe
    engine = create_async_engine(_ORACLE_URL, hide_parameters=True)
    recorded_at = datetime(2026, 10, 23, 12, 34, 56, 654321)
    try:
        async with engine.begin() as connection:
            result = await connection.execute(
                insert(table).values(
                    recorded_at=recorded_at,
                    expires_at=recorded_at.replace(tzinfo=timezone.utc),
                    token_hash=b"c" * 32,
                )
            )
            row = (await connection.execute(select(table))).one()
            primary_key = result.inserted_primary_key
            assert primary_key is not None
            assert row.id == primary_key[0]
            assert row.recorded_at == recorded_at
            assert row.expires_at == recorded_at.replace(tzinfo=timezone.utc)
            assert row.token_hash == b"c" * 32
    finally:
        await engine.dispose()


def test_oracle_server_default_returning_is_utc_in_non_utc_session(oracle_probe: tuple[Engine, Table]) -> None:
    engine, table = oracle_probe
    recorded_at = datetime(2026, 10, 23, 12, 34, 56, 123456)
    with engine.begin() as connection:
        connection.execute(text("ALTER SESSION SET TIME_ZONE = '-04:00'"))
        before = connection.scalar(select(func.sys_extract_utc(func.current_timestamp())))
        created_at = connection.scalar(
            insert(table)
            .values(recorded_at=recorded_at, expires_at=recorded_at, token_hash=b"e" * 32)
            .returning(table.c.created_at)
        )
        after = connection.scalar(select(func.sys_extract_utc(func.current_timestamp())))
        assert isinstance(created_at, datetime)
        assert created_at.tzinfo == timezone.utc
        assert before <= created_at.replace(tzinfo=None) <= after


def test_oracle_check_cli_preserves_existing_rows(oracle_probe: tuple[Engine, Table]) -> None:
    engine, table = oracle_probe
    with engine.begin() as connection:
        connection.execute(
            insert(table).values(
                recorded_at=datetime(2026, 10, 23),
                expires_at=datetime(2026, 10, 24, tzinfo=timezone.utc),
                token_hash=b"d" * 32,
            )
        )

    result = _run_database_cli(
        "oracle-check", "--pool-size", "4", "--max-overflow", "0", "--replicas", "2", "--extra-replicas", "1"
    )

    assert result.returncode == 0, result.stderr
    assert "unsupported" in result.stdout.lower() or "unverified" in result.stdout.lower()
    assert "16" in result.stdout
    assert "24" in result.stdout
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(table)) == 1
        assert connection.scalar(select(table.c.token_hash)) == b"d" * 32


def test_oracle_upgrade_cli_refuses_incomplete_backend(oracle_probe: tuple[Engine, Table]) -> None:
    engine, table = oracle_probe

    result = _run_database_cli("upgrade")

    assert result.returncode != 0
    assert "oracle-check" in result.stderr
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(table)) == 0


def test_oracle_check_cli_deadline_closes_a_stalled_native_connection() -> None:
    pytest.importorskip("oracledb")

    with socket.socket() as listener, ThreadPoolExecutor(max_workers=1) as executor:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(8)
        port = listener.getsockname()[1]

        def receive_without_reply() -> bool:
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(8)
                received = False
                try:
                    while connection.recv(65536):
                        received = True
                except ConnectionResetError:
                    pass
                return received

        closed = executor.submit(receive_without_reply)
        password = "probe-timeout-password"
        environment = {
            **os.environ,
            "CODEX_LB_DATABASE_URL": (f"oracle+oracledb://probe:{password}@127.0.0.1:{port}/?service_name=unused"),
        }
        started = time.monotonic()
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.db.migrate",
                "oracle-check",
                "--timeout-seconds",
                "1.5",
                "--pool-size",
                "4",
                "--max-overflow",
                "0",
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert time.monotonic() - started < 8
        if password in result.stdout or password in result.stderr:
            pytest.fail("Timeout diagnostics exposed a credential; captured output has been withheld.")
        assert result.returncode != 0
        assert "timed out" in (result.stdout + result.stderr).lower()
        # The child really reached the silent endpoint, then its socket closed
        # without the endpoint ever unblocking the native driver's operation.
        assert closed.result(timeout=8)


def test_oracle_schema_inventory_covers_empty_text_binds(oracle_probe: tuple[Engine, Table]) -> None:
    engine, _ = oracle_probe
    metadata = MetaData()
    table = Table(
        f"codex_text_{uuid4().hex[:12]}",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("optional_text", Text, nullable=True),
        Column("required_text", Text, nullable=False),
    )
    report = inspect_oracle_schema(metadata)
    assert {(blocker.kind, blocker.object_name) for blocker in report.blockers} == {
        (OracleSchemaBlockerKind.EMPTY_STRING_REPRESENTATION, "optional_text"),
        (OracleSchemaBlockerKind.EMPTY_STRING_REPRESENTATION, "required_text"),
    }

    try:
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(insert(table).values(id=1, optional_text="", required_text="present"))
            row = connection.execute(select(table.c.optional_text, table.c.optional_text.is_(None))).one()
            assert row[0] is None
            assert row[1] is True
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(insert(table).values(id=2, optional_text="present", required_text=""))
            assert connection.scalar(select(func.count()).select_from(table)) == 1
    finally:
        metadata.drop_all(engine)
