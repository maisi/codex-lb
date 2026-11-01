"""Offline Oracle DDL restart safety and dedicated lineage; no database connections."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import String

from app.db.migrate import _build_alembic_config
from app.db.oracle_baseline import OracleSchemaDriftError, load_oracle_baseline
from app.db.oracle_schema import oracle_head_contract


def _revision():
    script = ScriptDirectory.from_config(_build_alembic_config("oracle+oracledb://fixture:fixture@fixture.invalid"))
    assert script.get_heads() == ["20261101_000100_request_node"]
    revision = script.get_revision("head")
    assert revision is not None
    assert revision.down_revision == "20261024_000000_oracle_baseline"
    return revision.module


def test_oracle_revision_fits_the_native_alembic_version_ledger():
    migration = _revision()
    context = MigrationContext.configure(dialect_name="oracle")
    ledger_type = context._version.c.version_num.type
    assert isinstance(ledger_type, String)
    assert ledger_type.length is not None
    assert len(migration.revision) <= ledger_type.length


@pytest.mark.parametrize("existing", [None, ("VARCHAR2", 64, "B", "Y", None)])
def test_oracle_additive_node_column_resumes_after_ddl_commit(monkeypatch, existing):
    migration = _revision()
    connection = SimpleNamespace(
        execute=Mock(return_value=SimpleNamespace(first=lambda: existing)), exec_driver_sql=Mock()
    )
    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    migration.upgrade()
    if existing is None:
        connection.exec_driver_sql.assert_called_once_with(
            "ALTER TABLE request_logs ADD (processing_node VARCHAR2(64 BYTE) NULL)"
        )
    else:
        connection.exec_driver_sql.assert_not_called()


@pytest.mark.parametrize(
    "existing",
    [
        ("VARCHAR2", 32, "B", "Y", None),
        ("VARCHAR2", 64, "C", "Y", None),
        ("VARCHAR2", 64, "B", "N", None),
        ("VARCHAR2", 64, "B", "Y", "'private-host'"),
    ],
)
def test_oracle_node_migration_rejects_incompatible_existing_column(monkeypatch, existing):
    migration = _revision()
    connection = SimpleNamespace(
        execute=Mock(return_value=SimpleNamespace(first=lambda: existing)), exec_driver_sql=Mock()
    )
    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    with pytest.raises(OracleSchemaDriftError, match="incompatible existing column"):
        migration.upgrade()
    connection.exec_driver_sql.assert_not_called()


def test_oracle_contract_preserves_baseline_and_adds_only_nullable_node_column():
    baseline = load_oracle_baseline()
    head = oracle_head_contract()
    for parent, evolved in zip(baseline.tables, head.tables, strict=True):
        if parent.name != "request_logs":
            assert parent == evolved
            continue
        assert evolved.columns[:-1] == parent.columns
        node = evolved.columns[-1]
        assert (node.name, node.type_sql, node.nullable, node.default_sql) == (
            "processing_node",
            "VARCHAR2(64 BYTE)",
            True,
            None,
        )
    assert head.indexes == baseline.indexes


def test_oracle_node_downgrade_removes_only_new_column(monkeypatch):
    migration = _revision()
    drop = Mock()
    monkeypatch.setattr(migration.op, "drop_column", drop)
    migration.downgrade()
    drop.assert_called_once_with("request_logs", "processing_node")
