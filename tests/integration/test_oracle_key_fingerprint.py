"""Oracle first-boot key agreement through the existing startup verifier."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import Table, func, inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config.key_fingerprint import (
    ENCRYPTION_KEY_FINGERPRINT_SENTINEL,
    EncryptionKeyFingerprintMismatchError,
    compute_encryption_key_fingerprint,
    verify_encryption_key_fingerprint,
)
from app.db.models import RuntimeSentinel

_ORACLE_URL = os.environ.get("CODEX_LB_TEST_ORACLE_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _ORACLE_URL, reason="Set CODEX_LB_TEST_ORACLE_URL to an owned Oracle test schema."),
]


@pytest.fixture
async def oracle_sentinels() -> AsyncIterator[AsyncEngine]:
    pytest.importorskip("oracledb")
    engine = create_async_engine(_ORACLE_URL, hide_parameters=True, pool_size=4, max_overflow=0)
    table = cast(Table, RuntimeSentinel.__table__)
    created = False
    try:
        async with engine.begin() as connection:
            exists = await connection.run_sync(lambda connection: inspect(connection).has_table(table.name))
            if exists:
                pytest.fail("Oracle key tests require no existing runtime_sentinels table.")
            await connection.run_sync(table.create)
            created = True
        yield engine
    finally:
        try:
            if created:
                async with engine.begin() as connection:
                    await connection.run_sync(table.drop)
        finally:
            await engine.dispose()


@pytest.mark.parametrize("matching", [True, False], ids=["same-key", "different-keys"])
async def test_oracle_concurrent_first_boot_verifies_the_committed_key(
    oracle_sentinels: AsyncEngine, tmp_path: Path, matching: bool
) -> None:
    barrier = asyncio.Barrier(2)

    class SimultaneousFirstInsertSession(AsyncSession):
        async def execute(self, statement, *args: Any, **kwargs: Any) -> Any:
            if str(statement).upper().startswith("INSERT INTO RUNTIME_SENTINELS"):
                await asyncio.wait_for(barrier.wait(), timeout=5)
            return await super().execute(statement, *args, **kwargs)

    factory = async_sessionmaker(oracle_sentinels, class_=SimultaneousFirstInsertSession, expire_on_commit=False)
    first_key = tmp_path / "first.key"
    second_key = first_key if matching else tmp_path / "second.key"
    first_fingerprint = compute_encryption_key_fingerprint(first_key)
    second_fingerprint = compute_encryption_key_fingerprint(second_key)
    outcomes = await asyncio.gather(
        verify_encryption_key_fingerprint(factory, key_file=first_key, mode="enforce"),
        verify_encryption_key_fingerprint(factory, key_file=second_key, mode="enforce"),
        return_exceptions=True,
    )
    for outcome in outcomes:
        if isinstance(outcome, BaseException) and not isinstance(outcome, EncryptionKeyFingerprintMismatchError):
            raise outcome
    assert sum(outcome is None for outcome in outcomes) == (2 if matching else 1)
    assert sum(isinstance(outcome, EncryptionKeyFingerprintMismatchError) for outcome in outcomes) == (
        0 if matching else 1
    )
    async with oracle_sentinels.connect() as connection:
        stored = await connection.scalar(
            select(RuntimeSentinel.value).where(RuntimeSentinel.name == ENCRYPTION_KEY_FINGERPRINT_SENTINEL)
        )
        assert await connection.scalar(select(func.count()).select_from(RuntimeSentinel)) == 1
    expected = first_fingerprint if outcomes[0] is None else second_fingerprint
    assert stored == expected


async def test_oracle_key_mismatch_modes_preserve_existing_fingerprint(
    oracle_sentinels: AsyncEngine, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    factory = async_sessionmaker(oracle_sentinels, expire_on_commit=False)
    first_key, second_key = tmp_path / "first.key", tmp_path / "second.key"
    await verify_encryption_key_fingerprint(factory, key_file=first_key, mode="enforce")
    with pytest.raises(EncryptionKeyFingerprintMismatchError):
        await verify_encryption_key_fingerprint(factory, key_file=second_key, mode="enforce")
    with caplog.at_level(logging.ERROR, logger="app.core.config.key_fingerprint"):
        await verify_encryption_key_fingerprint(factory, key_file=second_key, mode="warn")
    assert "Encryption key mismatch" in caplog.text
    async with oracle_sentinels.connect() as connection:
        assert await connection.scalar(select(RuntimeSentinel.value)) == compute_encryption_key_fingerprint(first_key)

    def no_session() -> AsyncSession:
        pytest.fail("Off mode must skip database verification")

    await verify_encryption_key_fingerprint(no_session, key_file=second_key, mode="off")
