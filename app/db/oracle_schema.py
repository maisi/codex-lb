"""Read-only metadata review; this does not certify Oracle application support."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import Enum as SqlEnum
from sqlalchemy import MetaData, String, Text
from sqlalchemy.dialects import oracle

from app.db.models import Base


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


def inspect_oracle_schema(metadata: MetaData | None = None) -> OracleSchemaReport:
    """List model definitions needing an explicit Oracle representation decision.

    Nullable strings also need review: silently turning an empty value into NULL
    changes returned values and equality queries even without a NOT NULL error.
    Enumerations already reject empty values and Text maps to a separate LOB
    representation, so neither is treated as an unbounded VARCHAR.
    """
    selected_metadata = Base.metadata if metadata is None else metadata
    oracle_dialect = oracle.dialect()
    blockers: list[OracleSchemaBlocker] = []
    for table in sorted(selected_metadata.tables.values(), key=lambda table: table.fullname):
        for column in table.columns:
            column_type = column.type.dialect_impl(oracle_dialect)
            # Oracle-specific variants may already supply bounds or a LOB.
            if not isinstance(column_type, String) or isinstance(column_type, (Text, SqlEnum)):
                continue
            if column_type.length is None:
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
                    f"Oracle stores an empty VARCHAR as NULL; review {nullability} storage, equality and API values.",
                )
            )
        for index in sorted(table.indexes, key=lambda index: index.name or ""):
            predicates = [
                value for name, value in index.dialect_kwargs.items() if name in ("sqlite_where", "postgresql_where")
            ]
            if any(predicate is not None for predicate in predicates):
                blockers.append(
                    OracleSchemaBlocker(
                        OracleSchemaBlockerKind.PARTIAL_INDEX,
                        table.fullname,
                        index.name or "<unnamed>",
                        "Oracle does not preserve SQLite/PostgreSQL filtered index predicates; "
                        "design an equivalent index.",
                    )
                )
    return OracleSchemaReport(table_count=len(selected_metadata.tables), blockers=tuple(blockers))
