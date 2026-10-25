"""Destructive tests: this URL MUST identify a dedicated, disposable schema."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, insert, inspect, select, update
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.db.migrate import check_schema_drift, current_revision, run_upgrade
from app.db.models import (
    AccountUsageRollupState,
    AuditLog,
    DashboardRoleRecord,
    DashboardUser,
    DashboardUserInvite,
    ModelContextWindowOverride,
)
from app.db.oracle_baseline import OracleSchemaDriftError, load_oracle_baseline
from app.db.oracle_connection import create_oracle_sync_engine

_URL = os.environ.get("CODEX_LB_TEST_ORACLE_BASELINE_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _URL, reason="Set CODEX_LB_TEST_ORACLE_BASELINE_URL to a disposable, empty schema."),
]


@pytest.fixture
def baseline_engine() -> Iterator[Engine]:
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


def _upgrade() -> None:
    result = run_upgrade(_URL, bootstrap_legacy=False)
    assert result.current_revision == "20261024_000000_oracle_baseline"


def test_oracle_upgrade_seeds_verifies_and_preserves_rows_on_restart(baseline_engine: Engine) -> None:
    _upgrade()
    assert check_schema_drift(_URL) == ()
    with baseline_engine.begin() as connection:
        assert connection.scalar(select(func.count()).select_from(DashboardRoleRecord)) == 5
        connection.execute(
            insert(AuditLog).values(
                action="oracle_restart", details="preserve me", timestamp=datetime.now(timezone.utc)
            )
        )
    _upgrade()
    assert check_schema_drift(_URL) == ()
    with baseline_engine.connect() as connection:
        assert connection.scalar(select(AuditLog.details).where(AuditLog.action == "oracle_restart")) == "preserve me"
        state = connection.execute(select(AccountUsageRollupState.folded_through)).scalar_one()
        assert state == datetime(1970, 1, 1)


@pytest.mark.parametrize("interruption", ["CREATE TABLE request_logs", "CREATE INDEX idx_logs_requested_at_id"])
def test_oracle_interrupted_ddl_resumes_without_stamping_partial_schema(
    baseline_engine: Engine, monkeypatch: pytest.MonkeyPatch, interruption: str
) -> None:
    original = Connection.exec_driver_sql

    def fail_at_target(self: Connection, statement: str, *args, **kwargs):
        if statement.startswith(interruption):
            raise RuntimeError("Simulated interrupted Oracle DDL")
        return original(self, statement, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Connection, "exec_driver_sql", fail_at_target)
        with pytest.raises(RuntimeError, match="interrupted Oracle DDL"):
            _upgrade()
    assert current_revision(_URL) is None
    _upgrade()
    assert check_schema_drift(_URL) == ()


def test_oracle_interrupted_baseline_rejects_incompatible_surviving_columns(baseline_engine: Engine) -> None:
    with baseline_engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE accounts (id VARCHAR2(16 BYTE) PRIMARY KEY)")
    with pytest.raises(OracleSchemaDriftError, match="incompatible existing objects"):
        _upgrade()
    assert current_revision(_URL) is None


def test_oracle_drift_detects_changed_function_index_and_sequence(baseline_engine: Engine) -> None:
    _upgrade()
    with baseline_engine.begin() as connection:
        connection.exec_driver_sql("DROP INDEX uq_dashboard_user_invites_expected_identity")
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX uq_dashboard_user_invites_expected_identity ON dashboard_user_invites "
            "(expected_provider, expected_provider_key, expected_subject)"
        )
        connection.exec_driver_sql("ALTER SEQUENCE audit_logs_id_seq INCREMENT BY 2")
    diffs = check_schema_drift(_URL)
    assert "uq_dashboard_user_invites_expected_identity: index expressions differ" in diffs
    assert "audit_logs_id_seq: sequence increment or cycle differs" in diffs


def test_oracle_empty_strings_and_long_clobs_round_trip_and_compare_exactly(baseline_engine: Engine) -> None:
    _upgrade()
    instant = datetime(2026, 10, 24, 12, 34, 56, 123456, tzinfo=timezone.utc)
    prefix = "x" * 600
    values = ("", "\x01", "\x01\x01", prefix + "one", prefix + "two", "🦊" * 2000)
    with baseline_engine.begin() as connection:
        for key in ("", "\x01", "\x01\x01"):
            connection.execute(insert(ModelContextWindowOverride).values(slug=key, context_window=1000))
            assert (
                connection.scalar(select(ModelContextWindowOverride.slug).where(ModelContextWindowOverride.slug == key))
                == key
            )
        for offset, value in enumerate(values):
            connection.execute(insert(AuditLog).values(action=f"empty-{offset}", details=value, timestamp=instant))
        for offset, value in enumerate(values):
            row = connection.execute(
                select(AuditLog.action, AuditLog.details, AuditLog.timestamp).where(AuditLog.details == value)
            ).one()
            assert row.action == f"empty-{offset}"
            assert row.details == value
            assert row.timestamp == instant


def test_oracle_invite_unique_index_releases_identity_when_consumed(baseline_engine: Engine) -> None:
    _upgrade()
    instant = datetime(2026, 10, 24, tzinfo=timezone.utc)
    with baseline_engine.begin() as connection:
        role_id = connection.scalar(select(DashboardRoleRecord.id).where(DashboardRoleRecord.slug == "admin"))
        connection.execute(insert(DashboardUser).values(id="u1", username="one", display_name="one", role_id=role_id))
        connection.execute(insert(DashboardUser).values(id="u2", username="two", display_name="two", role_id=role_id))
        values = {
            "created_by_user_id": "creator",
            "expected_provider": "oidc",
            "expected_provider_key": "default",
            "expected_subject": "subject",
            "expires_at": instant,
        }
        connection.execute(insert(DashboardUserInvite).values(id="i1", user_id="u1", token_hash=b"a" * 32, **values))
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(
                    insert(DashboardUserInvite).values(id="i2", user_id="u2", token_hash=b"b" * 32, **values)
                )
        connection.execute(
            update(DashboardUserInvite).where(DashboardUserInvite.id == "i1").values(consumed_at=instant)
        )
        connection.execute(insert(DashboardUserInvite).values(id="i2", user_id="u2", token_hash=b"b" * 32, **values))
