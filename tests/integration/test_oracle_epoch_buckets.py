"""Oracle hour buckets agree with the half-open windows the rollup folds use."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import datetime

import pytest
from sqlalchemy import BigInteger, case, cast, func, literal, select, text
from sqlalchemy.dialects.oracle import TIMESTAMP
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.utils.sql import bucket_epoch_expr, oracle_epoch_expr
from app.db.oracle_connection import create_oracle_async_engine

_ORACLE_URL = os.environ.get("CODEX_LB_TEST_ORACLE_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _ORACLE_URL, reason="Set CODEX_LB_TEST_ORACLE_URL to an owned Oracle test schema."),
]

_EPOCH = datetime(1970, 1, 1)


@pytest.fixture
async def oracle_engine() -> AsyncIterator[AsyncEngine]:
    pytest.importorskip("oracledb")
    engine = create_oracle_async_engine(_ORACLE_URL, pool_size=1, max_overflow=0)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "value",
    [
        # The production row that wedged every fold: 08:00 is 1/3 day.
        datetime(2026, 10, 28, 8, 0, 0, 400_000),
        datetime(2026, 10, 28, 8, 0, 0),
        datetime(2026, 10, 28, 2, 0, 0, 999_000),
        datetime(2026, 10, 28, 7, 59, 59, 999_000),
        datetime(2026, 10, 28, 6, 0, 0),
    ],
)
async def test_first_second_of_an_hour_stays_in_that_hour(oracle_engine: AsyncEngine, value: datetime) -> None:
    timestamp = literal(value, TIMESTAMP())
    async with oracle_engine.connect() as connection:
        row = (
            await connection.execute(
                select(
                    cast(oracle_epoch_expr(timestamp), BigInteger),
                    cast(bucket_epoch_expr(timestamp, dialect="oracle", bucket_seconds=3600), BigInteger),
                )
            )
        ).one()

    whole_seconds = int((value - _EPOCH).total_seconds())
    assert row[0] == whole_seconds
    assert row[1] == whole_seconds // 3600 * 3600


async def test_every_hour_boundary_of_a_year_lands_in_its_own_bucket(oracle_engine: AsyncEngine) -> None:
    samples = (
        text(
            "WITH hours AS ("
            " SELECT TIMESTAMP '2026-01-01 00:00:00' + NUMTODSINTERVAL(LEVEL - 1, 'HOUR') AS h"
            " FROM dual CONNECT BY LEVEL <= 366 * 24)"
            " SELECT h AS ts, h AS hour_start FROM hours"
            " UNION ALL SELECT h + INTERVAL '0.5' SECOND, h FROM hours"
            " UNION ALL SELECT h + INTERVAL '3599.9' SECOND, h FROM hours"
        )
        .columns(ts=TIMESTAMP(), hour_start=TIMESTAMP())
        .subquery()
    )
    bucket = bucket_epoch_expr(samples.c.ts, dialect="oracle", bucket_seconds=3600)
    hour_start = oracle_epoch_expr(samples.c.hour_start)
    async with oracle_engine.connect() as connection:
        total, misplaced = (
            await connection.execute(
                select(func.count(), func.sum(case((bucket != hour_start, 1), else_=0))).select_from(samples)
            )
        ).one()

    assert total == 3 * 366 * 24
    assert misplaced == 0
