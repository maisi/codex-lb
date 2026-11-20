from contextlib import asynccontextmanager
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.utils.time import utcnow
from app.modules.runtime.oracle_maintenance import check_quota, request_maintenance
from app.modules.runtime.oracle_storage import GIB, OracleStorage, StorageOperation
from app.modules.runtime.schemas import OracleStorageStatus


def storage_for(free, *, acquired=True, state="idle", updated=None):
    store = MagicMock(spec=OracleStorage)
    current = OracleStorageStatus(
        level="critical" if free < 2 * GIB else "warning", free_bytes=free, maintenance=state, updated_at=updated
    )

    @asynccontextmanager
    async def lock():
        yield acquired

    def record(value):
        current.maintenance = value
        current.updated_at = utcnow()

    store.lock.side_effect = lock
    store.status = AsyncMock(return_value=current)
    store.mark.side_effect = record
    return store


@pytest.mark.parametrize(
    ("free", "expected"),
    [
        (None, "healthy"),
        (3 * GIB, "healthy"),
        (3 * GIB - 1, "warning"),
        (2 * GIB, "warning"),
        (2 * GIB - 1, "critical"),
        (0, "critical"),
    ],
)
async def test_measured_quota_boundaries(free, expected):
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.execute = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=(free, None, None, "DATA"))
    status = await OracleStorage(MagicMock(), connection).status()
    assert status.level == expected and status.free_bytes == free


async def test_manual_warning_and_automatic_threshold():
    store = storage_for(2 * GIB)
    await check_quota(store)
    store.operations.assert_not_awaited()
    assert (await request_maintenance(store)).maintenance == "queued"
    store.operations.return_value = []
    await check_quota(store)
    assert (await store.status()).maintenance == "no_gain"

    critical = storage_for(2 * GIB - 1)
    critical.operations.return_value = [StorageOperation("online", GIB, GIB)]
    critical.execute.side_effect = lambda op: setattr(critical.status.return_value, "free_bytes", 2 * GIB)
    await check_quota(critical)
    critical.execute.assert_awaited_once()
    assert (await critical.status()).maintenance == "completed"


async def test_reserved_workspace_and_replica_contention():
    blocked = storage_for(GIB)
    blocked.operations.return_value = [StorageOperation("online", GIB + 1, GIB)]
    await check_quota(blocked)
    blocked.execute.assert_not_awaited()
    assert (await blocked.status()).maintenance == "no_space"
    await check_quota(blocked)
    blocked.operations.assert_awaited_once()

    follower = storage_for(GIB, acquired=False)
    await check_quota(follower)
    await request_maintenance(follower)
    follower.mark.assert_not_awaited()
    follower.execute.assert_not_awaited()


async def test_partial_failure_is_reported_and_retried_only_after_cooldown():
    store = storage_for(GIB)
    first = StorageOperation("first", 1000, GIB)
    second = StorageOperation("second", 2000, GIB)
    store.operations.return_value = [first, second]
    store.execute.side_effect = [None, RuntimeError("DDL failed")]
    with pytest.raises(RuntimeError):
        await check_quota(store)
    assert (await store.status()).maintenance == "failed"
    await check_quota(store)
    assert store.execute.await_count == 2
    store.status.return_value.updated_at = utcnow() - timedelta(hours=2)
    store.operations.return_value = []
    await check_quota(store)
    assert (await store.status()).maintenance == "no_gain"


async def test_interrupted_maintenance_resamples_without_replaying_ddl():
    store = storage_for(GIB, state="running")
    await check_quota(store)
    store.execute.assert_not_awaited()
    assert (await store.status()).maintenance == "failed"
    await check_quota(store)
    store.operations.assert_not_awaited()
