from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.auth import dependencies as auth
from app.core.auth.dashboard_access import guest_principal
from app.db.session import get_session
from app.modules.runtime.oracle_storage import GIB, OracleStorage
from app.modules.runtime.schemas import OracleStorageStatus

pytestmark = pytest.mark.integration
_PATH = "/api/runtime/oracle-storage"


async def test_non_oracle_has_no_maintenance(async_client, monkeypatch):
    open_storage = AsyncMock()
    monkeypatch.setattr(OracleStorage, "open", open_storage)
    response = await async_client.get(_PATH)
    assert response.status_code == 200 and response.json() is None
    assert (await async_client.post(_PATH + "/maintenance")).status_code == 404
    open_storage.assert_not_awaited()


async def test_quota_warning_and_authorized_request(async_client, app_instance, monkeypatch):
    from app.modules.runtime import api

    session = MagicMock()
    session.get_bind.return_value.dialect.name = "oracle"
    store = MagicMock(spec=OracleStorage)
    warning = OracleStorageStatus(level="warning", free_bytes=2 * GIB)
    store.status.return_value = warning
    monkeypatch.setattr(OracleStorage, "open", AsyncMock(return_value=store))
    enqueue = AsyncMock(return_value=warning.model_copy(update={"maintenance": "queued"}))
    monkeypatch.setattr(api, "request_maintenance", enqueue)
    with monkeypatch.context() as patch:
        patch.setitem(app_instance.dependency_overrides, get_session, lambda: session)
        response = await async_client.get(_PATH)
        assert response.status_code == 200 and response.json()["freeBytes"] == 2 * GIB
        response = await async_client.post(_PATH + "/maintenance")
        assert response.status_code == 200 and response.json()["maintenance"] == "queued"
        patch.setattr(auth, "validate_dashboard_session", AsyncMock(return_value=guest_principal()))
        assert (await async_client.post(_PATH + "/maintenance")).status_code == 403
    enqueue.assert_awaited_once()


async def test_postgres_skips_oracle_and_probe_failure_is_visible(async_client, app_instance, monkeypatch):
    session = MagicMock()
    session.get_bind.return_value.dialect.name = "postgresql"
    monkeypatch.setitem(app_instance.dependency_overrides, get_session, lambda: session)
    probe = AsyncMock(side_effect=RuntimeError("probe failed"))
    monkeypatch.setattr(OracleStorage, "open", probe)
    assert (await async_client.get(_PATH)).json() is None
    assert (await async_client.post(_PATH + "/maintenance")).status_code == 404
    probe.assert_not_awaited()
    session.get_bind.return_value.dialect.name = "oracle"
    response = await async_client.get(_PATH)
    assert response.status_code == 200 and response.json()["level"] == "unavailable"
