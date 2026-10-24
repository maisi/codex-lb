"""Oracle MERGE for rollups serialized by the shared fold-state row lock."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import Table, and_, func, literal, select, union_all
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import ClauseElement, ColumnElement, Executable, Select
from sqlalchemy.sql.compiler import SQLCompiler


class OracleMerge(Executable, ClauseElement):
    """An insert/select merge; callers own transaction and serialization.

    This statement deliberately does not retry concurrent first insertions.
    Its callers already hold the fold-state lock for the complete mutation.
    """

    inherit_cache = False

    def __init__(
        self,
        table: Table,
        source: Select,
        columns: Sequence[str],
        keys: Sequence[str],
        *,
        add: Sequence[str] = (),
        replace: Sequence[str] = (),
        minimum: Sequence[str] = (),
    ) -> None:
        self.table = table
        self.columns = tuple(columns)
        self.keys = tuple(keys)
        self.add = tuple(add)
        self.replace = tuple(replace)
        self.minimum = tuple(minimum)
        self.source = source.with_only_columns(
            *(column.label(name) for column, name in zip(source.selected_columns, self.columns, strict=True))
        ).subquery("excluded")


def merge_values(
    table: Table,
    rows: Sequence[Mapping[str, Any]],
    keys: Sequence[str],
    *,
    add: Sequence[str] = (),
    replace: Sequence[str] = (),
) -> OracleMerge:
    """Use typed SELECT binds, including the Oracle-only empty-value encoding."""
    if not rows:
        raise ValueError("Oracle merge requires at least one row")
    columns = tuple(rows[0])
    selects = [select(*(literal(row[name], type_=table.c[name].type).label(name) for name in columns)) for row in rows]
    source = selects[0] if len(selects) == 1 else select(union_all(*selects).subquery())
    return OracleMerge(table, source, columns, keys, add=add, replace=replace)


@compiles(OracleMerge, "oracle")
def _compile_merge(statement: OracleMerge, compiler: SQLCompiler, **kwargs: Any) -> str:
    table = statement.table
    source = statement.source
    target_sql = compiler.preparer.format_table(table)
    source_sql = compiler.process(source, asfrom=True, **kwargs)
    condition = and_(*(table.c[name] == source.c[name] for name in statement.keys))
    sql = f"MERGE INTO {target_sql} USING {source_sql} ON ({compiler.process(condition, **kwargs)})"
    updates: list[tuple[str, ColumnElement]] = [(name, table.c[name] + source.c[name]) for name in statement.add]
    updates.extend((name, source.c[name]) for name in statement.replace)
    updates.extend((name, func.least(table.c[name], source.c[name])) for name in statement.minimum)
    if updates:
        assignments = ", ".join(
            f"{compiler.preparer.quote(name)} = {compiler.process(value, **kwargs)}" for name, value in updates
        )
        sql += f" WHEN MATCHED THEN UPDATE SET {assignments}"
    names = ", ".join(compiler.preparer.quote(name) for name in statement.columns)
    values = ", ".join(compiler.process(source.c[name], **kwargs) for name in statement.columns)
    return sql + f" WHEN NOT MATCHED THEN INSERT ({names}) VALUES ({values})"
