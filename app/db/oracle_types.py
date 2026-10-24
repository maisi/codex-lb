"""Dialect variants that leave the existing SQLite/PostgreSQL schema intact."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKeyConstraint, LargeBinary, MetaData, String, Text, func, literal_column
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.oracle import CLOB, RAW, TIMESTAMP, VARCHAR2
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.schema import CreateColumn, CreateIndex
from sqlalchemy.sql import operators
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.sql.elements import BinaryExpression, BindParameter, ColumnElement, False_, True_
from sqlalchemy.sql.functions import GenericFunction
from sqlalchemy.types import TypeDecorator


class _UTCProjection(GenericFunction[datetime]):
    inherit_cache = True
    _register = False


@compiles(_UTCProjection)
def _compile_utc_projection(element: _UTCProjection, compiler: SQLCompiler, **kwargs: Any) -> str:
    return compiler.process(element.clauses, **kwargs)


@compiles(_UTCProjection, "oracle")
def _compile_oracle_utc_projection(element: _UTCProjection, compiler: SQLCompiler, **kwargs: Any) -> str:
    return f"sys_extract_utc({compiler.process(element.clauses, **kwargs)})"


class _AwareDateTime(DateTime):
    def column_expression(self, colexpr: ColumnElement[datetime]) -> ColumnElement[datetime]:
        # Oracle's RETURNING compiler checks the generic type rather than its
        # dialect variant, so this hook must also exist before adaptation.
        return _UTCProjection(colexpr, type_=self)


class _OracleUTCDateTime(TypeDecorator[datetime]):
    """Preserve aware instants despite the driver's timezone-naive datetimes."""

    impl = TIMESTAMP(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None or value.utcoffset() is None:
            # The application also supplies naive UTC through utcnow().
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def bind_expression(self, bindparam: BindParameter[datetime]) -> ColumnElement[datetime]:
        # Do not let Oracle interpret the normalized timestamp in SESSIONTIMEZONE.
        return func.from_tz(bindparam, literal_column("'+00:00'"), type_=self)

    def column_expression(self, column: ColumnElement[datetime]) -> ColumnElement[datetime]:
        # Also handles values produced by CURRENT_TIMESTAMP in a non-UTC session.
        return func.sys_extract_utc(column, type_=self)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=timezone.utc)


def database_datetime(*, timezone: bool = False) -> DateTime:
    # Oracle's generic DateTime mapping is DATE, which discards microseconds.
    oracle_type = _OracleUTCDateTime() if timezone else TIMESTAMP()
    generic_type = _AwareDateTime(timezone=True) if timezone else DateTime()
    return generic_type.with_variant(oracle_type, "oracle")


def sha256_binary() -> LargeBinary:
    # A BLOB cannot implement the invitation token's unique equality lookup.
    return LargeBinary().with_variant(RAW(32), "oracle")


_EMPTY_STRING = "\x01"


class OracleStringStorage(TypeDecorator[str]):
    """Keep Python empty strings distinct from NULL, including sentinel inputs.

    Oracle folds a zero-length VARCHAR/CLOB bind into NULL. A single control
    character stores the empty string, and doubling an initial control
    character makes the representation reversible for every input value.
    Bound comparisons use the same codec as writes.
    """

    impl = String
    cache_ok = True

    def __init__(self, *, byte_length: int | None = None, large_text: bool = False) -> None:
        self.byte_length = byte_length
        self.large_text = large_text
        super().__init__()

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        return dialect.type_descriptor(CLOB() if self.large_text else VARCHAR2(self.byte_length))

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        stored = _EMPTY_STRING if not value else _EMPTY_STRING + value if value.startswith(_EMPTY_STRING) else value
        if self.byte_length is not None and len(stored.encode("utf-8")) > self.byte_length:
            raise ValueError(f"Oracle string exceeds its {self.byte_length}-byte storage limit")
        return stored

    def process_result_value(self, value: str | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return value[1:] if value.startswith(_EMPTY_STRING) else value


def configure_oracle_string_storage(metadata: MetaData) -> None:
    """Install Oracle-only storage without changing SQLite/PostgreSQL DDL.

    Previously unbounded identifiers receive 1024 bytes. Existing character
    contracts reserve four UTF-8 bytes per character plus one escape byte.
    Unindexed URLs use a CLOB to preserve their 2048-character API contract.
    """
    for table in metadata.tables.values():
        for column in table.columns:
            original = column.type
            if not isinstance(original, String) or isinstance(original, SqlEnum):
                continue
            large_text = isinstance(original, Text) or (table.name, column.name) == ("model_sources", "base_url")
            byte_length = None if large_text else 4 * original.length + 1 if original.length else 1024
            if (table.name, column.name) == ("accounts", "email"):
                byte_length = 1281  # 320 Unicode code points, as accepted by dashboard identity fields.
            column.type = original.with_variant(
                OracleStringStorage(byte_length=byte_length, large_text=large_text), "oracle"
            )


@compiles(OracleStringStorage, "oracle")
def _compile_oracle_string_storage(element: OracleStringStorage, compiler: SQLCompiler, **kwargs: Any) -> str:
    return "CLOB" if element.large_text else f"VARCHAR2({element.byte_length} BYTE)"


@compiles(CreateIndex, "oracle")
def _compile_oracle_filtered_index(element: CreateIndex, compiler: Any, **kwargs: Any) -> str:
    index = element.element
    predicate = index.dialect_options["postgresql"].get("where")
    has_lob = any(
        not isinstance(expression, str) and isinstance(expression.type, Text) for expression in index.expressions
    )
    if predicate is None and not has_lob:
        return compiler.visit_create_index(element, **kwargs)
    condition = (
        None if predicate is None else compiler.sql_compiler.process(predicate, literal_binds=True, include_table=False)
    )
    expressions: list[str] = []
    for expression in index.expressions:
        value = compiler.sql_compiler.process(expression, literal_binds=True, include_table=False)
        direction = " DESC" if value.endswith(" DESC") else ""
        if direction:
            value = value[:-5]
        if not isinstance(expression, str) and isinstance(expression.type, Text):
            value = f"DBMS_LOB.SUBSTR({value}, 512, 1)"
        if condition is not None:
            value = f"CASE WHEN {condition} THEN {value} END"
        expressions.append(value + direction)
    unique = "UNIQUE " if index.unique else ""
    return (
        f"CREATE {unique}INDEX {compiler.preparer.format_index(index)} "
        f"ON {compiler.preparer.format_table(index.table)} ({', '.join(expressions)})"
    )


class _DatabaseEpoch(GenericFunction[datetime]):
    inherit_cache = True
    _register = False


@compiles(_DatabaseEpoch)
def _compile_database_epoch(element: _DatabaseEpoch, compiler: SQLCompiler, **kwargs: Any) -> str:
    return "'1970-01-01 00:00:00'"


@compiles(_DatabaseEpoch, "oracle")
def _compile_oracle_database_epoch(element: _DatabaseEpoch, compiler: SQLCompiler, **kwargs: Any) -> str:
    return "TIMESTAMP '1970-01-01 00:00:00'"


def database_epoch_default() -> ColumnElement[datetime]:
    return _DatabaseEpoch()


@compiles(ForeignKeyConstraint, "oracle")
def _compile_oracle_foreign_key(element: ForeignKeyConstraint, compiler: Any, **kwargs: Any) -> str:
    # Oracle's default immediate NO ACTION has the intended RESTRICT behavior;
    # the explicit RESTRICT spelling itself is not legal Oracle DDL.
    return compiler.visit_foreign_key_constraint(element, **kwargs).replace(" ON DELETE RESTRICT", "")


@compiles(BinaryExpression, "oracle")
def _compile_oracle_lob_comparison(element: BinaryExpression, compiler: SQLCompiler, **kwargs: Any) -> str:
    if element.operator in (operators.is_, operators.is_not) and isinstance(element.right, (True_, False_)):
        # SQLAlchemy stores Oracle Boolean as SMALLINT but otherwise renders
        # ``IS 1``/``IS 0``, which Oracle rejects. Retain two-valued IS semantics
        # for NULL as well, including negation and nested conditions.
        left = compiler.process(element.left, **kwargs)
        value = 1 if isinstance(element.right, True_) else 0
        if element.operator is operators.is_:
            return f"({left} = {value} AND {left} IS NOT NULL)"
        return f"({left} <> {value} OR {left} IS NULL)"
    storage = element.left.type.dialect_impl(compiler.dialect)
    if (
        not isinstance(storage, OracleStringStorage)
        or not storage.large_text
        or element.operator not in (operators.eq, operators.ne)
    ):
        return compiler.visit_binary(element, **kwargs)
    left = compiler.process(element.left, **kwargs)
    right = compiler.process(element.right, **kwargs)
    comparison = f"DBMS_LOB.COMPARE({left}, {right}) {'=' if element.operator is operators.eq else '<>'} 0"
    if element.operator is operators.ne:
        return comparison
    # The prefix predicate selects candidates using the nonunique prefix
    # index; the full comparison remains authoritative for arbitrarily long
    # values and strings sharing that prefix.
    return f"(DBMS_LOB.SUBSTR({left}, 512, 1) = DBMS_LOB.SUBSTR({right}, 512, 1) AND {comparison})"


@compiles(CreateColumn, "oracle")
def _compile_oracle_empty_string_default(element: CreateColumn, compiler: Any, **kwargs: Any) -> str:
    compiled = compiler.visit_create_column(element, **kwargs)
    storage = element.element.type.dialect_impl(compiler.dialect)
    if isinstance(storage, OracleStringStorage):
        compiled = compiled.replace(" DEFAULT ''", " DEFAULT CHR(1)", 1)
    return compiled
