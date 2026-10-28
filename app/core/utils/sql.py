"""Shared timestamp expressions for the supported SQL dialects."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Date, Integer, cast, func, literal_column
from sqlalchemy.sql import ColumnExpressionArgument
from sqlalchemy.sql.elements import ColumnElement


def oracle_epoch_expr(timestamp: ColumnExpressionArgument[datetime]) -> ColumnElement[Any]:
    """Whole UTC seconds since the Unix epoch for an Oracle timestamp.

    The DATE cast truncates to whole seconds, but the day difference is a
    decimal NUMBER: 08:00 is 1/3 day, so ``* 86400`` lands a hair below the
    hour and a later FLOOR puts the hour's first second into the previous
    bucket. ROUND restores the exact integer the cast already guarantees.
    """
    return func.round((cast(timestamp, Date) - literal_column("DATE '1970-01-01'")) * 86400)


def bucket_epoch_expr(
    timestamp: ColumnExpressionArgument[datetime], *, dialect: str, bucket_seconds: int
) -> ColumnElement[Any]:
    if bucket_seconds <= 0:
        raise ValueError("bucket_seconds must be positive")
    if dialect == "oracle":
        # Oracle DATE subtraction yields days. Cast only after UTC pool setup;
        # flooring retains the whole-second bucket contract of SQLite/PG.
        epoch = oracle_epoch_expr(timestamp)
        return func.floor(epoch / bucket_seconds) * bucket_seconds
    if dialect == "postgresql":
        return func.floor(func.extract("epoch", timestamp) / bucket_seconds) * bucket_seconds
    epoch = cast(func.strftime("%s", timestamp), Integer)
    return cast(epoch / bucket_seconds, Integer) * bucket_seconds
