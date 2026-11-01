"""Offline Oracle storage contracts and read-only model inventory."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

from sqlalchemy import Column, DefaultClause, MetaData, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects import oracle
from sqlalchemy.engine import Dialect
from sqlalchemy.sql.elements import ColumnElement, UnaryExpression

from app.db.models import Base
from app.db.oracle_baseline import OracleColumn, OracleSnapshot, load_oracle_baseline
from app.db.oracle_types import OracleStringStorage


class OracleSchemaBlockerKind(StrEnum):
    UNBOUNDED_STRING = "unbounded_string"
    PARTIAL_INDEX = "partial_index"
    EMPTY_STRING_REPRESENTATION = "empty_string_representation"


@dataclass(frozen=True, slots=True)
class OracleSchemaBlocker:
    kind: OracleSchemaBlockerKind
    table_name: str
    object_name: str
    detail: str


@dataclass(frozen=True, slots=True)
class OracleSchemaReport:
    table_count: int
    blockers: tuple[OracleSchemaBlocker, ...]


def oracle_head_contract() -> OracleSnapshot:
    """Evolve read-only catalog expectations; migrations still own their frozen DDL."""
    baseline = load_oracle_baseline()
    node = OracleColumn(name="processing_node", type_sql="VARCHAR2(64 BYTE)", nullable=True)
    tables = tuple(
        table.model_copy(update={"columns": (*table.columns, node)}) if table.name == "request_logs" else table
        for table in baseline.tables
    )
    return baseline.model_copy(update={"tables": tables})


def inspect_oracle_schema(metadata: MetaData | None = None) -> OracleSchemaReport:
    """List model definitions lacking an explicit Oracle representation.

    Nullable strings also need review: silently turning an empty value into NULL
    changes returned values and equality queries even without a NOT NULL error.
    Enumerations already reject empty values. Text maps to a LOB rather than an
    unbounded VARCHAR, but binding an empty Python string still stores NULL and
    needs an explicit representation decision.
    """
    selected_metadata = Base.metadata if metadata is None else metadata
    oracle_dialect = oracle.dialect()
    blockers: list[OracleSchemaBlocker] = []
    for table in sorted(selected_metadata.tables.values(), key=lambda table: table.fullname):
        for column in table.columns:
            column_type = column.type.dialect_impl(oracle_dialect)
            # Oracle-specific variants may already supply bounds or a LOB.
            if not isinstance(column_type, String) or isinstance(column_type, SqlEnum):
                continue
            if column_type.length is None and not isinstance(column_type, Text):
                blockers.append(
                    OracleSchemaBlocker(
                        OracleSchemaBlockerKind.UNBOUNDED_STRING,
                        table.fullname,
                        column.name,
                        "Oracle VARCHAR2 needs an explicit size; choose a validated bound or a LOB representation.",
                    )
                )
            nullability = "NOT NULL" if not column.nullable else "nullable"
            blockers.append(
                OracleSchemaBlocker(
                    OracleSchemaBlockerKind.EMPTY_STRING_REPRESENTATION,
                    table.fullname,
                    column.name,
                    f"Oracle stores an empty Python string bind as NULL; "
                    f"review {nullability} storage, equality and API values.",
                )
            )
    return OracleSchemaReport(table_count=len(selected_metadata.tables), blockers=tuple(blockers))


def _default_sql(column: Column[Any], dialect: Dialect) -> str | None:
    default = column.server_default
    if default is None:
        return None
    if not isinstance(default, DefaultClause):
        raise TypeError(f"Unsupported server default for {column}")
    storage = column.type.dialect_impl(dialect)
    if isinstance(storage, OracleStringStorage) and str(default.arg) in {"", "''"}:
        return "CHR(1)"
    return (
        repr(default.arg)
        if isinstance(default.arg, str)
        else str(default.arg.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
    )


def oracle_snapshot_from_metadata(metadata: MetaData | None = None) -> OracleSnapshot:
    """Render a schema contract for offline review and current-model drift checks.

    Migrations load their checked-in snapshot and never invoke this renderer.
    """
    from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Sequence, UniqueConstraint
    from sqlalchemy.schema import CreateIndex, CreateSequence, CreateTable

    from app.db.oracle_baseline import (
        OracleColumn,
        OracleForeignKey,
        OracleIndex,
        OracleSequence,
        OracleSnapshot,
        OracleTable,
    )

    selected = Base.metadata if metadata is None else metadata
    dialect = oracle.dialect()
    tables = []
    indexes = []
    sequences: dict[str, OracleSequence] = {}
    seen_indexes: set[tuple[str, tuple[str, ...], bool]] = set()
    for table in selected.sorted_tables:
        for column in table.c:
            if isinstance(column.default, Sequence):
                sequence = column.default
                sequences[str(sequence.name)] = OracleSequence(
                    name=str(sequence.name), ddl=str(CreateSequence(sequence).compile(dialect=dialect)).strip()
                )
        tables.append(
            OracleTable(
                name=table.name,
                ddl=str(CreateTable(table).compile(dialect=dialect)).strip(),
                columns=tuple(
                    OracleColumn(
                        name=column.name,
                        type_sql=str(column.type.compile(dialect=dialect)),
                        nullable=bool(column.nullable),
                        default_sql=_default_sql(column, dialect),
                    )
                    for column in table.c
                ),
                primary_key=tuple(column.name for column in table.primary_key.columns),
                unique_constraints=tuple(
                    sorted(
                        tuple(column.name for column in constraint.columns)
                        for constraint in table.constraints
                        if isinstance(constraint, UniqueConstraint)
                    )
                ),
                foreign_keys=tuple(
                    sorted(
                        (
                            OracleForeignKey(
                                columns=tuple(element.parent.name for element in constraint.elements),
                                target_table=constraint.elements[0].column.table.name,
                                target_columns=tuple(element.column.name for element in constraint.elements),
                                ondelete=None if constraint.ondelete == "RESTRICT" else constraint.ondelete,
                            )
                            for constraint in table.constraints
                            if isinstance(constraint, ForeignKeyConstraint)
                        ),
                        key=lambda item: cast(OracleForeignKey, item).columns,
                    )
                ),
                checks=tuple(
                    sorted(
                        str(constraint.sqltext.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
                        for constraint in table.constraints
                        if isinstance(constraint, CheckConstraint)
                    )
                ),
            )
        )
        seen_indexes.add((table.name, tuple(column.name for column in table.primary_key.columns), True))
        seen_indexes.update(
            (table.name, tuple(column.name for column in constraint.columns), True)
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        )
        for index in sorted(table.indexes, key=lambda value: value.name or ""):
            ddl = str(CreateIndex(index).compile(dialect=dialect)).strip()
            predicate = index.dialect_options["postgresql"].get("where")
            condition = None if predicate is None else str(predicate.compile(dialect=dialect))
            expressions = []
            for untyped_expression in index.expressions:
                expression = cast(ColumnElement[Any], untyped_expression)
                value = str(
                    expression.compile(dialect=dialect, compile_kwargs={"literal_binds": True, "include_table": False})
                )
                descending = value.endswith(" DESC")
                if descending:
                    value = value[:-5]
                if isinstance(expression.type, Text):
                    value = f"DBMS_LOB.SUBSTR({value}, 512, 1)"
                if condition is not None:
                    value = f"CASE WHEN {condition} THEN {value} END"
                value_type = cast(UnaryExpression, expression).element.type if descending else expression.type
                if isinstance(value_type, DateTime) and value_type.timezone:
                    value = f"SYS_EXTRACT_UTC({value})"
                if descending:
                    value += " DESC"
                expressions.append(value)
            signature = (table.name, tuple(expressions), bool(index.unique))
            if signature in seen_indexes or (
                not index.unique and (table.name, tuple(expressions), True) in seen_indexes
            ):
                continue
            seen_indexes.add(signature)
            indexes.append(
                OracleIndex(
                    name=str(index.name),
                    table_name=table.name,
                    ddl=ddl,
                    unique=bool(index.unique),
                    expressions=tuple(expressions),
                )
            )
    return OracleSnapshot(tables=tuple(tables), indexes=tuple(indexes), sequences=tuple(sequences.values()))
