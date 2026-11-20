from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.modules.shared.schemas import DashboardModel


class RuntimeVersionResponse(DashboardModel):
    current_version: str
    latest_version: str | None = None
    update_available: bool = False
    checked_at: datetime
    source: str | None = None
    release_url: str = "https://github.com/Soju06/codex-lb/releases/latest"


OracleStorageLevel = Literal["healthy", "warning", "critical", "unavailable"]
OracleMaintenanceState = Literal["idle", "queued", "running", "completed", "no_space", "no_gain", "failed"]


class OracleStorageStatus(DashboardModel):
    level: OracleStorageLevel
    free_bytes: int | None = None
    maintenance: OracleMaintenanceState = "idle"
    updated_at: datetime | None = None
