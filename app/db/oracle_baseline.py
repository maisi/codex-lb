"""Oracle's immutable baseline, restartable DDL, and catalog drift validation."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection


class _SnapshotModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class OracleColumn(_SnapshotModel):
    name: str
    type_sql: str
    nullable: bool
    default_sql: str | None = None


class OracleForeignKey(_SnapshotModel):
    columns: tuple[str, ...]
    target_table: str
    target_columns: tuple[str, ...]
    ondelete: str | None = None


class OracleTable(_SnapshotModel):
    name: str
    ddl: str
    columns: tuple[OracleColumn, ...]
    primary_key: tuple[str, ...]
    unique_constraints: tuple[tuple[str, ...], ...]
    foreign_keys: tuple[OracleForeignKey, ...]
    checks: tuple[str, ...]


class OracleIndex(_SnapshotModel):
    name: str
    table_name: str
    ddl: str
    unique: bool
    expressions: tuple[str, ...]


class OracleSequence(_SnapshotModel):
    name: str
    ddl: str


class OracleSnapshot(_SnapshotModel):
    tables: tuple[OracleTable, ...]
    indexes: tuple[OracleIndex, ...]
    sequences: tuple[OracleSequence, ...]
    seeds: tuple[str, ...] = ()


class OracleSchemaDriftError(RuntimeError):
    pass


def load_oracle_baseline() -> OracleSnapshot:
    path = Path(__file__).parent / "oracle_alembic" / "baseline_v1.json"
    return OracleSnapshot.model_validate_json(path.read_text())


def _sql_identity(value: str | None) -> str:
    if value is None:
        return ""
    # Oracle quotes catalog identifiers and inserts whitespace; quoted string
    # literals retain their exact case and content.
    value = re.sub(r"CASE\s+WHEN\s*\((.*?)\)\s+THEN", r"CASE WHEN \1 THEN", value, flags=re.IGNORECASE)
    parts = re.split(r"('(?:''|[^'])*')", value.strip())
    return "".join(
        part if offset % 2 else re.sub(r'\s+|"', "", part).upper().replace("SYS.DBMS_LOB.", "DBMS_LOB.")
        for offset, part in enumerate(parts)
    )


def _type_identity(type_sql: str) -> str:
    value = type_sql.upper().replace("VARCHAR(", "VARCHAR2(")
    if value in {"INTEGER", "SMALLINT"}:
        value = "NUMBER(*,0)"
    if value == "FLOAT":
        value = "FLOAT(126)"
    if value == "NUMBER(19)":
        value = "NUMBER(19,0)"
    if value.startswith("TIMESTAMP") and not value.startswith("TIMESTAMP("):
        value = value.replace("TIMESTAMP", "TIMESTAMP(6)", 1)
    return _sql_identity(value)


def _catalog_column_type(row: tuple) -> str:
    name, data_type, data_length, precision, scale, char_length, char_used, nullable, default = row
    if data_type == "VARCHAR2":
        return f"VARCHAR2({char_length} {'CHAR' if char_used == 'C' else 'BYTE'})"
    if data_type == "NUMBER":
        return ("NUMBER(*,0)" if scale == 0 else "NUMBER") if precision is None else f"NUMBER({precision},{scale or 0})"
    if data_type == "FLOAT":
        return f"FLOAT({precision})"
    if data_type == "RAW":
        return f"RAW({data_length})"
    return str(data_type)


def _table_drift(connection: Connection, table: OracleTable) -> list[str]:
    inspector = inspect(connection)
    rows = connection.execute(
        text(
            "SELECT column_name, data_type, data_length, data_precision, data_scale, "
            "char_length, char_used, nullable, data_default FROM user_tab_columns "
            "WHERE table_name = :name ORDER BY column_id"
        ),
        {"name": table.name.upper()},
    ).all()
    actual = {str(row[0]).lower(): row for row in rows}
    diffs: list[str] = []
    expected_names = {column.name for column in table.columns}
    if set(actual) != expected_names:
        diffs.append(
            f"{table.name}: columns differ (missing={sorted(expected_names - actual.keys())}, "
            f"unexpected={sorted(actual.keys() - expected_names)})"
        )
    for column in table.columns:
        row = actual.get(column.name)
        if row is None:
            continue
        if _type_identity(_catalog_column_type(tuple(row))) != _type_identity(column.type_sql):
            diffs.append(f"{table.name}.{column.name}: storage type differs")
        if (row[7] == "Y") != column.nullable:
            diffs.append(f"{table.name}.{column.name}: nullability differs")
        if _sql_identity(row[8]) != _sql_identity(column.default_sql):
            diffs.append(f"{table.name}.{column.name}: server default differs")
    primary_key = tuple(inspector.get_pk_constraint(table.name)["constrained_columns"])
    if primary_key != table.primary_key:
        diffs.append(f"{table.name}: primary key differs")
    unique_constraints = {tuple(item["column_names"]) for item in inspector.get_unique_constraints(table.name)}
    if unique_constraints != set(table.unique_constraints):
        diffs.append(f"{table.name}: unique constraints differ")
    foreign_keys = {
        (
            tuple(item["constrained_columns"]),
            item["referred_table"],
            tuple(item["referred_columns"]),
            item.get("options", {}).get("ondelete"),
        )
        for item in inspector.get_foreign_keys(table.name)
    }
    expected_fks = {
        (item.columns, item.target_table, item.target_columns, item.ondelete) for item in table.foreign_keys
    }
    if foreign_keys != expected_fks:
        diffs.append(f"{table.name}: foreign keys differ")
    checks = {
        _sql_identity(item["sqltext"])
        for item in inspector.get_check_constraints(table.name)
        if not re.fullmatch(r'"?\w+"? IS NOT NULL', item["sqltext"], re.IGNORECASE)
    }
    if checks != {_sql_identity(item) for item in table.checks}:
        diffs.append(f"{table.name}: check constraints differ")
    return diffs


def oracle_schema_drift(
    connection: Connection, snapshot: OracleSnapshot, *, allow_missing: bool = False
) -> tuple[str, ...]:
    """Check catalog definitions, including function-index expressions and sequences."""
    inspector = inspect(connection)
    existing_tables = set(inspector.get_table_names())
    expected_tables = {table.name for table in snapshot.tables}
    diffs = [f"unexpected table: {name}" for name in sorted(existing_tables - expected_tables - {"alembic_version"})]
    for table in snapshot.tables:
        if table.name in existing_tables:
            diffs.extend(_table_drift(connection, table))
        elif not allow_missing:
            diffs.append(f"missing table: {table.name}")
    index_rows = connection.execute(
        text("SELECT index_name, table_name, uniqueness, index_type FROM user_indexes")
    ).all()
    indexes = {str(row[0]).lower(): row for row in index_rows}
    expected_indexes = {index.name for index in snapshot.indexes}
    constraint_indexes = {
        str(row[0]).lower()
        for row in connection.execute(
            text(
                "SELECT index_name FROM user_constraints WHERE constraint_type IN ('P', 'U') AND index_name IS NOT NULL"
            )
        )
    }
    diffs.extend(
        f"unexpected index: {name}"
        for name, row in indexes.items()
        if name not in expected_indexes and name not in constraint_indexes and row[3] != "LOB"
    )
    for index in snapshot.indexes:
        actual = indexes.get(index.name)
        if actual is None:
            if not allow_missing:
                diffs.append(f"missing index: {index.name}")
            continue
        if str(actual[1]).lower() != index.table_name or (actual[2] == "UNIQUE") != index.unique:
            diffs.append(f"{index.name}: index ownership or uniqueness differs")
        expressions = connection.execute(
            text(
                "SELECT c.column_name, c.descend, e.column_expression FROM user_ind_columns c "
                "LEFT JOIN user_ind_expressions e ON e.index_name = c.index_name "
                "AND e.column_position = c.column_position WHERE c.index_name = :name ORDER BY c.column_position"
            ),
            {"name": index.name.upper()},
        ).all()
        actual_exprs = tuple(
            _sql_identity(str(row[2] if row[2] is not None else row[0]) + (" DESC" if row[1] == "DESC" else ""))
            for row in expressions
        )
        if actual_exprs != tuple(_sql_identity(value) for value in index.expressions):
            diffs.append(f"{index.name}: index expressions differ")
    sequences = set(inspector.get_sequence_names())
    expected_sequences = {sequence.name for sequence in snapshot.sequences}
    diffs.extend(f"unexpected sequence: {name}" for name in sorted(sequences - expected_sequences))
    if not allow_missing:
        diffs.extend(f"missing sequence: {name}" for name in sorted(expected_sequences - sequences))
    for name in expected_sequences & sequences:
        row = connection.execute(
            text("SELECT increment_by, cycle_flag FROM user_sequences WHERE sequence_name = :name"),
            {"name": name.upper()},
        ).one()
        if row[0] != 1 or row[1] != "N":
            diffs.append(f"{name}: sequence increment or cycle differs")
    return tuple(diffs)


def apply_oracle_baseline(connection: Connection) -> None:
    """Execute the revision-pinned snapshot, resuming only identical prior DDL."""
    snapshot = load_oracle_baseline()
    drift = oracle_schema_drift(connection, snapshot, allow_missing=True)
    if drift:
        raise OracleSchemaDriftError("Refusing Oracle baseline on incompatible existing objects: " + "; ".join(drift))
    inspector = inspect(connection)
    sequences = set(inspector.get_sequence_names())
    tables = set(inspector.get_table_names())
    indexes = {str(row[0]).lower() for row in connection.execute(text("SELECT index_name FROM user_indexes"))}
    for sequence in snapshot.sequences:
        if sequence.name not in sequences:
            connection.exec_driver_sql(sequence.ddl)
    for table in snapshot.tables:
        if table.name not in tables:
            connection.exec_driver_sql(table.ddl)
    for index in snapshot.indexes:
        if index.name not in indexes:
            connection.exec_driver_sql(index.ddl)
    drift = oracle_schema_drift(connection, snapshot)
    if drift:
        raise OracleSchemaDriftError("Oracle baseline verification failed: " + "; ".join(drift))
    for statement in snapshot.seeds:
        connection.exec_driver_sql(statement)
