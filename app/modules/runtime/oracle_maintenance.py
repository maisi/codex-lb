"""Run operator-requested and low-quota maintenance outside dashboard requests."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from app.core.utils.time import utcnow
from app.db.session import get_background_session
from app.modules.runtime.oracle_storage import GIB, OracleStorage
from app.modules.runtime.schemas import OracleMaintenanceState, OracleStorageStatus

logger = logging.getLogger(__name__)
_RETRY_AFTER = timedelta(hours=1)


def _due(status: OracleStorageStatus) -> bool:
    if status.maintenance in ("queued", "running"):
        return True
    if status.level != "critical":
        return False
    return status.updated_at is None or utcnow() - status.updated_at >= _RETRY_AFTER


async def request_maintenance(storage: OracleStorage) -> OracleStorageStatus:
    async with storage.lock() as acquired:
        status = await storage.status()
        if acquired and status.level in ("warning", "critical") and status.maintenance != "queued":
            await storage.mark("queued")
            return await storage.status()
        return status


async def _recover(storage: OracleStorage, initial_free: int | None) -> OracleMaintenanceState:
    blocked = False
    executed = False
    for operation in await storage.operations():
        status = await storage.status()
        if status.level == "healthy":
            return "completed"
        if operation.reclaimable_bytes < GIB // 8:
            continue
        if status.free_bytes is None or status.free_bytes < operation.working_bytes:
            blocked = True
            continue
        await storage.execute(operation)
        executed = True
    final = await storage.status()
    if final.level == "healthy":
        return "completed"
    if blocked:
        return "no_space"
    if executed and initial_free is not None and final.free_bytes is not None and final.free_bytes > initial_free:
        return "completed"
    return "no_gain"


async def check_quota(storage: OracleStorage) -> None:
    if not _due(await storage.status()):
        return
    async with storage.lock() as acquired:
        if not acquired:
            return
        status = await storage.status()
        if not _due(status):
            return
        if status.level == "healthy":
            await storage.mark("idle")
            return
        if status.maintenance == "running":
            # Obtaining the lock proves the previous runner lost its session. Its
            # last DDL may have committed. Re-sample after the shared retry delay.
            await storage.mark("failed")
            return
        await storage.mark("running")
        try:
            outcome = await _recover(storage, status.free_bytes)
        except Exception:
            await storage.mark("failed")
            raise
        await storage.mark(outcome)
        logger.info("Oracle quota maintenance finished outcome=%s", outcome)


class OracleQuotaWorker:
    def __init__(self) -> None:
        self.task = asyncio.create_task(self._run(), name="oracle-quota-maintenance")

    async def _run(self) -> None:
        while True:
            try:
                async with get_background_session() as session:
                    await check_quota(await OracleStorage.open(session))
            except Exception:
                logger.exception("Oracle quota check or maintenance failed")
            await asyncio.sleep(60)

    async def stop(self) -> None:
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
