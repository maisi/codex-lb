from __future__ import annotations

import pytest
from sqlalchemy import Column, MetaData, String, Table, Text, select
from sqlalchemy.dialects import oracle, postgresql, sqlite
from sqlalchemy.schema import CreateIndex

from app.db.models import Base
from app.db.oracle_baseline import load_oracle_baseline
from app.db.oracle_schema import oracle_head_contract, oracle_snapshot_from_metadata
from app.db.oracle_types import OracleStringStorage, configure_oracle_string_storage


def test_oracle_baseline_is_frozen_and_matches_current_model_contract() -> None:
    baseline = load_oracle_baseline()
    expected_head = oracle_head_contract()
    current = oracle_snapshot_from_metadata()

    assert len(baseline.tables) == len(Base.metadata.tables) == 68
    assert "processing_node" not in {
        column.name for table in baseline.tables if table.name == "request_logs" for column in table.columns
    }
    for expected, actual in zip(expected_head.tables, current.tables, strict=True):
        # Constraint-set ordering in emitted DDL is deliberately insignificant.
        assert expected.model_copy(
            update={"ddl": "", "columns": tuple(sorted(expected.columns, key=lambda c: c.name))}
        ) == actual.model_copy(update={"ddl": "", "columns": tuple(sorted(actual.columns, key=lambda c: c.name))})
    assert baseline.indexes == current.indexes
    assert baseline.sequences == current.sequences
    assert len(baseline.seeds) == 12


@pytest.mark.parametrize("value", [None, "", "plain", "\x01", "\x01prefixed", "\x01\x01", "Grüße 🦊"])
@pytest.mark.parametrize("large_text", [False, True])
def test_oracle_strings_have_collision_free_empty_value_storage(value: str | None, large_text: bool) -> None:
    storage = OracleStringStorage(byte_length=None if large_text else 1024, large_text=large_text)
    stored = storage.process_bind_param(value, oracle.dialect())

    assert stored != ""
    assert (stored is None) == (value is None)
    assert storage.process_result_value(stored, oracle.dialect()) == value


def test_oracle_string_limits_count_utf8_bytes_and_never_truncate() -> None:
    storage = OracleStringStorage(byte_length=1024)
    assert storage.process_bind_param("🦊" * 256, oracle.dialect()) == "🦊" * 256
    with pytest.raises(ValueError, match="1024-byte"):
        storage.process_bind_param("🦊" * 257, oracle.dialect())


def test_clob_equality_preserves_full_values_and_adds_prefix_index_predicate() -> None:
    metadata = MetaData()
    table = Table("document", metadata, Column("value", Text))
    configure_oracle_string_storage(metadata)
    statement = select(table.c.value).where(table.c.value == "long value")

    compiled = str(statement.compile(dialect=oracle.dialect()))
    assert "DBMS_LOB.COMPARE" in compiled
    assert "DBMS_LOB.SUBSTR" in compiled
    for dialect in (sqlite.dialect(), postgresql.dialect()):
        assert "DBMS_LOB" not in str(statement.compile(dialect=dialect))


def test_oracle_invitation_index_preserves_only_open_identity_uniqueness() -> None:
    index = next(index for index in Base.metadata.tables["dashboard_user_invites"].indexes if index.unique)
    compiled = str(CreateIndex(index).compile(dialect=oracle.dialect()))

    assert compiled.startswith("CREATE UNIQUE INDEX")
    assert compiled.count("CASE WHEN consumed_at IS NULL AND revoked_at IS NULL THEN") == 3


def test_oracle_empty_server_defaults_use_the_reversible_storage_value() -> None:
    from sqlalchemy import text
    from sqlalchemy.schema import CreateTable

    metadata = MetaData()
    table = Table("empty_default", metadata, Column("value", String, nullable=False, server_default=text("''")))
    configure_oracle_string_storage(metadata)

    assert "DEFAULT CHR(1)" in str(CreateTable(table).compile(dialect=oracle.dialect()))
    assert "DEFAULT ''" in str(CreateTable(table).compile(dialect=sqlite.dialect()))
    assert oracle_snapshot_from_metadata(metadata).tables[0].columns[0].default_sql == "CHR(1)"
