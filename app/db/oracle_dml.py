"""Oracle insert races with transaction ownership left to repositories."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from sqlalchemy import CursorResult, Table, insert, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import Base
from app.db.oracle_errors import is_oracle_unique_violation


async def oracle_insert_if_absent(session: AsyncSession, model: type[Base], values: Mapping[str, Any]) -> bool:
    """Insert without swallowing foreign-key, nullability or other errors."""
    try:
        async with session.begin_nested():
            await session.execute(insert(model).values(**values))
        return True
    except IntegrityError as exc:
        if not is_oracle_unique_violation(exc):
            raise
        return False


async def oracle_upsert(
    session: AsyncSession,
    model: type[Base],
    *,
    keys: Sequence[str],
    values: Mapping[str, Any],
    update_values: Mapping[str, Any],
    where: ColumnElement[bool] | None = None,
) -> bool:
    """Update or insert, retrying a concurrent first insert under a savepoint.

    A conditional update that loses its predicate returns false. Unlike MERGE,
    a unique-key race on an absent row retries against the committed winner.
    The enclosing transaction (including earlier writes) remains caller-owned.
    """
    table = cast(Table, model.__table__)
    conditions = [table.c[key] == values[key] for key in keys]
    if where is not None:
        conditions.append(where)
    statement = update(model).where(*conditions).values(**update_values)
    for _ in range(3):
        result = await session.execute(statement)
        if cast(CursorResult[Any], result).rowcount:
            return True
        if await oracle_insert_if_absent(session, model, values):
            return True
        if where is not None:
            result = await session.execute(statement)
            return cast(CursorResult[Any], result).rowcount > 0
    raise RuntimeError(f"Oracle upsert could not establish a row in {table.name}")
