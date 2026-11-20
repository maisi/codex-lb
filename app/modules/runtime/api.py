from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dashboard_access import Permission
from app.core.auth.dependencies import (
    require_dashboard_permission,
    set_dashboard_error_format,
    validate_dashboard_session,
)
from app.db.session import get_session
from app.modules.runtime.oracle_maintenance import request_maintenance
from app.modules.runtime.oracle_storage import OracleStorage
from app.modules.runtime.schemas import OracleStorageStatus, RuntimeVersionResponse
from app.modules.runtime.service import get_runtime_version_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/runtime",
    tags=["runtime"],
    dependencies=[Depends(validate_dashboard_session), Depends(set_dashboard_error_format)],
)


@router.get("/version", response_model=RuntimeVersionResponse)
async def get_runtime_version() -> RuntimeVersionResponse:
    return await get_runtime_version_service().get_version_status()


@router.get("/oracle-storage", dependencies=[Depends(require_dashboard_permission(Permission.DASHBOARD_READ))])
async def oracle_storage_status(session: AsyncSession = Depends(get_session)) -> OracleStorageStatus | None:
    if session.get_bind().dialect.name != "oracle":
        return None
    try:
        storage = await OracleStorage.open(session)
        return await storage.status()
    except Exception:
        logger.exception("Cannot sample Oracle schema quota")
        return OracleStorageStatus(level="unavailable")


@router.post("/oracle-storage/maintenance", dependencies=[Depends(require_dashboard_permission(Permission.OPS_WRITE))])
async def queue_oracle_maintenance(session: AsyncSession = Depends(get_session)) -> OracleStorageStatus:
    if session.get_bind().dialect.name != "oracle":
        raise HTTPException(status_code=404, detail="Oracle storage maintenance is unavailable")
    return await request_maintenance(await OracleStorage.open(session))
