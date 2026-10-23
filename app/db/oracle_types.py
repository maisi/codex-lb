"""Dialect variants that leave the existing SQLite/PostgreSQL schema intact."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, LargeBinary, func, literal_column
from sqlalchemy.dialects.oracle import RAW, TIMESTAMP
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.sql.elements import BindParameter, ColumnElement
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
