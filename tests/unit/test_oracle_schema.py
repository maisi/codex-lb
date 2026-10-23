from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Sequence,
    String,
    Table,
    Text,
    create_engine,
    insert,
    select,
    text,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects import oracle, postgresql, sqlite
from sqlalchemy.engine import Dialect
from sqlalchemy.schema import CreateIndex, CreateSequence, CreateTable

from app.db.models import Base, DashboardUserInvite, UsageHistory
from app.db.oracle_schema import OracleSchemaBlockerKind, inspect_oracle_schema
from app.db.oracle_types import database_datetime


def test_all_model_timestamps_preserve_oracle_microseconds_and_timezone() -> None:
    columns = [
        column for table in Base.metadata.tables.values() for column in table.c if isinstance(column.type, DateTime)
    ]

    assert columns
    for column in columns:
        assert isinstance(column.type, DateTime)
        expected = "TIMESTAMP WITH TIME ZONE" if column.type.timezone else "TIMESTAMP"
        assert column.type.compile(dialect=oracle.dialect()) == expected, str(column)


def test_invite_token_hash_has_indexable_oracle_binary_representation() -> None:
    table = cast(Table, DashboardUserInvite.__table__)
    column = table.c.token_hash

    assert column.type.compile(dialect=oracle.dialect()) == "RAW(32)"
    assert column.type.compile(dialect=postgresql.dialect()) == "BYTEA"
    assert column.type.compile(dialect=sqlite.dialect()) == "BLOB"
    assert "UNIQUE (token_hash)" in str(CreateTable(table).compile(dialect=oracle.dialect()))


def test_aware_timestamp_conversion_is_oracle_only_in_select_and_returning() -> None:
    table = Table("sample", MetaData(), Column("expires_at", database_datetime(timezone=True)))
    statements = [select(table.c.expires_at), insert(table).values(expires_at=None).returning(table.c.expires_at)]

    for statement in statements:
        assert "sys_extract_utc" in str(statement.compile(dialect=oracle.dialect()))
        for dialect in (sqlite.dialect(), postgresql.dialect()):
            sql = str(statement.compile(dialect=dialect))
            assert "sys_extract_utc" not in sql
            assert "from_tz" not in sql


@pytest.mark.parametrize("dialect", [sqlite.dialect(), postgresql.dialect()], ids=["sqlite", "postgresql"])
def test_existing_backend_ddl_matches_pre_oracle_type_and_id_definitions(dialect: Dialect) -> None:
    legacy_metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        legacy_table = table.to_metadata(legacy_metadata)
        for column in legacy_table.columns:
            if isinstance(column.type, DateTime):
                column.type = DateTime(timezone=column.type.timezone)
            if isinstance(column.type, LargeBinary):
                column.type = LargeBinary()
            if isinstance(column.default, Sequence):
                column.default = None

    for table in Base.metadata.sorted_tables:
        legacy_table = legacy_metadata.tables[table.fullname]
        # SQLAlchemy copies the unordered constraint set in a different order.
        actual_lines = str(CreateTable(table).compile(dialect=dialect)).splitlines()
        legacy_lines = str(CreateTable(legacy_table).compile(dialect=dialect)).splitlines()
        assert sorted(line.strip().rstrip(",") for line in actual_lines) == sorted(
            line.strip().rstrip(",") for line in legacy_lines
        )
        legacy_indexes = {index.name: index for index in legacy_table.indexes}
        for index in table.indexes:
            assert str(CreateIndex(index).compile(dialect=dialect)) == str(
                CreateIndex(legacy_indexes[index.name]).compile(dialect=dialect)
            )


def test_generated_ids_use_oracle_sequences_and_existing_backend_generation() -> None:
    generated_ids = [
        table.c.id for table in Base.metadata.tables.values() if "id" in table.c and table.c.id.autoincrement is True
    ]

    assert generated_ids
    for column in generated_ids:
        sequence = cast(Sequence, column.default)
        assert isinstance(sequence, Sequence)
        assert sequence.optional is True
        assert str(CreateSequence(sequence).compile(dialect=oracle.dialect())) == f"CREATE SEQUENCE {sequence.name}"
        statement = insert(column.table).values({})
        assert f"{sequence.name}.nextval" in str(statement.compile(dialect=oracle.dialect()))
        assert ".nextval" not in str(statement.compile(dialect=sqlite.dialect()))
        assert ".nextval" not in str(statement.compile(dialect=postgresql.dialect()))
        assert "SERIAL" in str(CreateTable(column.table).compile(dialect=postgresql.dialect()))


def test_sqlite_generated_model_ids_still_increment_without_explicit_ids() -> None:
    engine = create_engine("sqlite:///:memory:")
    try:
        table = cast(Table, UsageHistory.__table__)
        table.create(engine)
        with engine.begin() as connection:
            first = connection.execute(insert(table).values(account_id="account", used_percent=1.0))
            second = connection.execute(insert(table).values(account_id="account", used_percent=2.0))
            assert first.inserted_primary_key == (1,)
            assert second.inserted_primary_key == (2,)
    finally:
        engine.dispose()


def test_schema_report_identifies_representation_decisions_without_mutating_metadata() -> None:
    metadata = MetaData()
    table = Table(
        "example",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("key", String, nullable=False),
        Column("alias", String(32), nullable=True),
        Column("description", Text),
        Column("state", SqlEnum("active", "paused")),
        Column("bounded_variant", String().with_variant(String(16), "oracle")),
    )
    index = Index(
        "uq_example_active_key",
        table.c.key,
        unique=True,
        sqlite_where=text("state = 'active'"),
        postgresql_where=text("state = 'active'"),
    )
    original_ddl = str(CreateTable(table).compile(dialect=sqlite.dialect()))
    original_index = str(CreateIndex(index).compile(dialect=sqlite.dialect()))

    report = inspect_oracle_schema(metadata)

    assert report.table_count == 1
    assert {(blocker.kind, blocker.object_name) for blocker in report.blockers} == {
        (OracleSchemaBlockerKind.UNBOUNDED_STRING, "key"),
        (OracleSchemaBlockerKind.EMPTY_STRING_REPRESENTATION, "key"),
        (OracleSchemaBlockerKind.EMPTY_STRING_REPRESENTATION, "alias"),
        (OracleSchemaBlockerKind.EMPTY_STRING_REPRESENTATION, "description"),
        (OracleSchemaBlockerKind.EMPTY_STRING_REPRESENTATION, "bounded_variant"),
        (OracleSchemaBlockerKind.PARTIAL_INDEX, "uq_example_active_key"),
    }
    assert all(blocker.table_name == "example" for blocker in report.blockers)
    assert "NOT NULL" in next(
        blocker.detail
        for blocker in report.blockers
        if blocker.object_name == "key" and blocker.kind == OracleSchemaBlockerKind.EMPTY_STRING_REPRESENTATION
    )
    assert str(CreateTable(table).compile(dialect=sqlite.dialect())) == original_ddl
    assert str(CreateIndex(index).compile(dialect=sqlite.dialect())) == original_index


def test_application_schema_report_keeps_invite_uniqueness_and_rollup_empty_keys_explicit() -> None:
    report = inspect_oracle_schema()
    blockers = {(blocker.kind, blocker.table_name, blocker.object_name) for blocker in report.blockers}

    assert report.table_count == len(Base.metadata.tables)
    assert (OracleSchemaBlockerKind.UNBOUNDED_STRING, "accounts", "id") in blockers
    assert (
        OracleSchemaBlockerKind.PARTIAL_INDEX,
        "dashboard_user_invites",
        "uq_dashboard_user_invites_expected_identity",
    ) in blockers
    assert (
        OracleSchemaBlockerKind.EMPTY_STRING_REPRESENTATION,
        "request_report_hourly_rollups",
        "api_key_id",
    ) in blockers
    assert inspect_oracle_schema() == report
