from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select, update

from app.core.balancer.logic import ERROR_BACKOFF_THRESHOLD
from app.core.clients.proxy import ProxyResponseError
from app.db.models import ApiKeyUsageReservation, HttpBridgeOperationRecord
from app.db.session import SessionLocal
from app.dependencies import get_proxy_service_for_app
from app.modules.proxy import service as proxy_module
from app.modules.proxy._service.http_bridge import streaming
from app.modules.proxy.durable_bridge_repository import DurableBridgeRepository
from tests.integration.test_http_responses_bridge import (
    _cleanup_http_bridge_sessions as cleanup_http_bridge_sessions,  # noqa: F401
)
from tests.integration.test_http_responses_bridge import (
    _ClosingBridgeUpstreamWebSocket,
    _FakeBridgeUpstreamWebSocket,
    _get_account,
    _import_account,
    _install_bridge_settings,
    _install_proxy_settings,
    _make_app_settings,
    _make_dashboard_settings,
)
from tests.simulation.virtual_time import VirtualClock

pytestmark = pytest.mark.integration


def _user(text):
    return {"role": "user", "content": [{"type": "input_text", "text": text}]}


async def _post(client, path, input_items, *, anchor=None, headers=None):
    body = {"model": "gpt-5.1", "instructions": "Return OK.", "input": input_items, "prompt_cache_key": "recovery"}
    if anchor is not None:
        body["previous_response_id"] = anchor
    if path.startswith("/backend-api"):
        body["stream"] = True
    response = await asyncio.wait_for(client.post(path, json=body, headers=headers), timeout=5)
    if response.status_code != 200:
        return response, None
    if path.startswith("/backend-api"):
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: {")]
        completed = [event["response"] for event in events if event.get("type") == "response.completed"]
        return response, completed[-1] if completed else None
    return response, response.json()


@pytest_asyncio.fixture
async def recovery_transport(async_client, app_instance, monkeypatch):
    _install_bridge_settings(monkeypatch, enabled=True)
    owner_id = await _import_account(async_client, "recovery-owner", "owner@example.com")
    owner = await _get_account(owner_id)
    owner_upstream = _ClosingBridgeUpstreamWebSocket("resp_owner")
    replacement = _FakeBridgeUpstreamWebSocket("resp_replacement")
    connections = []

    async def ensure_fresh(self, account, *, force=False, timeout_seconds):
        return account

    async def connect(headers, access_token, account_id_header, *, base_url=None, session=None):
        connections.append((account_id_header, dict(headers)))
        return owner_upstream if account_id_header == owner.chatgpt_account_id else replacement

    monkeypatch.setattr(proxy_module.ProxyService, "_ensure_fresh_with_budget", ensure_fresh)
    monkeypatch.setattr(proxy_module, "connect_responses_websocket", connect)
    return get_proxy_service_for_app(app_instance), owner, owner_upstream, replacement, connections


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/v1/responses", "/backend-api/codex/responses"])
async def test_delta_relocates_from_complete_spool_and_keeps_new_owner(async_client, recovery_transport, path):
    service, owner, owner_upstream, replacement, connections = recovery_transport
    first, first_body = await _post(async_client, path, [_user("first")])
    assert first.status_code == 200, first.text
    await service.drain_persistence_tasks(timeout_seconds=5)
    async with SessionLocal() as session:
        repository = DurableBridgeRepository(session)
        operation = await repository.get_operation_by_response_id(response_id=first_body["id"])
        assert operation is not None
        assert operation.event_spool_complete
        assert operation.request_text is not None
        assert operation.parent_response_id is None
        assert await repository.get_operation_events(operation_id=operation.operation_id)
    transcript = await service._durable_bridge.get_replayable_transcript(response_id=first_body["id"])
    assert transcript is not None
    alternate_id = await _import_account(async_client, "recovery-alternate", "alternate@example.com")
    alternate = await _get_account(alternate_id)
    assert (await async_client.post(f"/api/accounts/{owner.id}/pause")).status_code == 200
    headers = {"session_id": "stale-session", "thread-id": "stale-thread", "x-request-trace": "preserve"}
    second, second_body = await _post(async_client, path, [_user("second")], anchor=first_body["id"], headers=headers)
    assert second.status_code == 200, second.text
    assert second_body["id"] == "resp_replacement_1"
    assert len(owner_upstream.sent_text) == len(replacement.sent_text) == 1
    replay = json.loads(replacement.sent_text[0])
    assert "previous_response_id" not in replay
    assert replay["input"] == [_user("first"), first_body["output"][0], _user("second")]
    assert [connection[0] for connection in connections] == [owner.chatgpt_account_id, alternate.chatgpt_account_id]
    assert connections[-1][1]["x-request-trace"] == "preserve"
    assert not {"session_id", "thread-id", "x-codex-turn-state"} & connections[-1][1].keys()
    third, third_body = await _post(async_client, path, [_user("third")], anchor=second_body["id"])
    assert third.status_code == 200, third.text
    assert third_body["id"] == "resp_replacement_2"
    assert len(connections) == 2
    assert json.loads(replacement.sent_text[1])["previous_response_id"] == second_body["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["incomplete_spool", "orphan_tool", "single_account", "foreign_scope", "file_pin"])
async def test_unsafe_reconstruction_never_dispatches_to_another_account(
    async_client, recovery_transport, monkeypatch, fault
):
    service, owner, owner_upstream, replacement, connections = recovery_transport
    first, first_body = await _post(async_client, "/v1/responses", [_user("first")])
    assert first.status_code == 200
    await service.drain_persistence_tasks(timeout_seconds=5)
    await _import_account(async_client, "recovery-alternate", "alternate@example.com")
    assert (await async_client.post(f"/api/accounts/{owner.id}/pause")).status_code == 200
    if fault in ("incomplete_spool", "foreign_scope"):
        async with SessionLocal() as session:
            values = {"event_spool_complete": False} if fault == "incomplete_spool" else {"account_id": "foreign-owner"}
            await session.execute(
                update(HttpBridgeOperationRecord)
                .where(HttpBridgeOperationRecord.response_id == first_body["id"])
                .values(**values)
            )
            await session.commit()
    if fault == "single_account":
        dashboard = _make_dashboard_settings()
        dashboard.routing_strategy = "single_account"
        dashboard.single_account_id = owner.id
        _install_proxy_settings(
            monkeypatch, app_settings=_make_app_settings(enabled=True), dashboard_settings=dashboard
        )
    current = (
        [{"type": "function_call_output", "call_id": "orphan", "output": "ok"}]
        if fault == "orphan_tool"
        else [_user("second")]
    )
    if fault == "file_pin":
        await service._pin_file_account("file-owned", owner.id)
        current[0]["content"].append({"type": "input_file", "file_id": "file-owned"})
    second, body = await _post(async_client, "/v1/responses", current, anchor=first_body["id"])
    assert second.status_code in ((503,) if fault == "single_account" else (502, 503)), second.text
    assert body is None
    if fault != "file_pin":
        assert second.json()["error"]["code"] == (
            "continuity_owner_policy_conflict" if fault == "single_account" else "previous_response_owner_unavailable"
        )
    assert len(owner_upstream.sent_text) == len(connections) == 1
    assert replacement.sent_text == []


@pytest.mark.asyncio
async def test_connect_failure_does_not_reconstruct_or_dispatch_to_replacement(
    async_client, recovery_transport, monkeypatch
):
    service, _, _, replacement, _ = recovery_transport
    first, first_body = await _post(async_client, "/v1/responses", [_user("first")])
    assert first.status_code == 200
    await service.drain_persistence_tasks(timeout_seconds=5)
    await _import_account(async_client, "recovery-alternate", "alternate@example.com")
    loader = AsyncMock(return_value=None)
    monkeypatch.setattr(streaming, "load_transcript_replay", loader)

    async def fail_connect(*args, **kwargs):
        raise ProxyResponseError(502, {"error": {"code": "upstream_connect_error", "message": "connect failed"}})

    monkeypatch.setattr(proxy_module, "connect_responses_websocket", fail_connect)
    second, _ = await _post(async_client, "/v1/responses", [_user("second")], anchor=first_body["id"])
    assert second.status_code == 502, second.text
    loader.assert_not_called()
    assert replacement.sent_text == []


@pytest.mark.asyncio
async def test_active_owner_backoff_wait_reselects_same_anchor_without_capacity_lease(
    async_client, recovery_transport, monkeypatch
):
    service, owner, owner_upstream, replacement, _ = recovery_transport
    first, first_body = await _post(async_client, "/v1/responses", [_user("first")])
    assert first.status_code == 200
    await service.drain_persistence_tasks(timeout_seconds=5)
    balancer = service._load_balancer
    await balancer.record_errors(owner, 1, minimum_error_count=ERROR_BACKOFF_THRESHOLD)
    real_delay = streaming.continuity_owner_recovery_delay
    observed_delays = []

    async def short_backoff(load_balancer, account_id):
        delay = await real_delay(load_balancer, account_id)
        assert delay is not None and 0 < delay <= 30
        observed_delays.append(delay)
        lock = await load_balancer._get_account_lock(account_id)
        assert not lock.locked()
        assert await load_balancer.account_pressure_snapshot(account_id) == (0, 0, 0.0)
        load_balancer._runtime[account_id].last_error_at -= 31
        return 0.001

    monkeypatch.setattr(streaming, "continuity_owner_recovery_delay", short_backoff)
    second, second_body = await _post(async_client, "/v1/responses", [_user("second")], anchor=first_body["id"])
    assert second.status_code == 200, second.text
    assert second_body["id"] == "resp_owner_2"
    assert len(observed_delays) == 1
    assert json.loads(owner_upstream.sent_text[1])["previous_response_id"] == first_body["id"]
    assert replacement.sent_text == []


@pytest.mark.asyncio
async def test_persistent_backoff_has_one_bounded_wait_window(async_client, recovery_transport, monkeypatch):
    service, owner, owner_upstream, _, _ = recovery_transport
    first, first_body = await _post(async_client, "/v1/responses", [_user("first")])
    assert first.status_code == 200
    await service.drain_persistence_tasks(timeout_seconds=5)
    await service._load_balancer.record_errors(owner, 5, minimum_error_count=ERROR_BACKOFF_THRESHOLD)
    monkeypatch.setattr(streaming, "_CONTINUITY_OWNER_RECOVERY_MAX_WAIT_SECONDS", 0.01)
    loader = AsyncMock(return_value=None)
    monkeypatch.setattr(streaming, "load_transcript_replay", loader)
    second, _ = await _post(async_client, "/v1/responses", [_user("second")], anchor=first_body["id"])
    assert second.status_code == 502, second.text
    assert len(owner_upstream.sent_text) == 1
    loader.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancellation_during_owner_wait_leaves_no_bridge_creation(async_client, recovery_transport, monkeypatch):
    service, owner, owner_upstream, _, connections = recovery_transport
    first, first_body = await _post(async_client, "/v1/responses", [_user("first")])
    assert first.status_code == 200
    await service.drain_persistence_tasks(timeout_seconds=5)
    await service._load_balancer.record_errors(owner, 1, minimum_error_count=ERROR_BACKOFF_THRESHOLD)
    waiting = asyncio.Event()
    original_wait = streaming._iter_account_capacity_wait_sse

    async def signal_wait(**kwargs):
        waiting.set()
        async for event in original_wait(**kwargs):
            yield event

    monkeypatch.setattr(streaming, "_iter_account_capacity_wait_sse", signal_wait)
    task = asyncio.create_task(_post(async_client, "/v1/responses", [_user("second")], anchor=first_body["id"]))
    try:
        await asyncio.wait_for(waiting.wait(), timeout=5)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert len(owner_upstream.sent_text) == len(connections) == 1
    assert not service._http_bridge_inflight_sessions
    assert not (await service._load_balancer._get_account_lock(owner.id)).locked()
    assert await service._load_balancer.account_pressure_snapshot(owner.id) == (0, 0, 0.0)


@pytest.mark.asyncio
async def test_owner_wait_is_capped_by_original_request_deadline(async_client, recovery_transport, monkeypatch):
    service, owner, owner_upstream, replacement, _ = recovery_transport
    first, first_body = await _post(async_client, "/v1/responses", [_user("first")])
    assert first.status_code == 200
    await service.drain_persistence_tasks(timeout_seconds=5)
    clock = VirtualClock(monotonic_value=service._clock.monotonic(), epoch_value=service._clock.time())
    service._clock = clock
    service._load_balancer._clock = clock
    await service._load_balancer.record_errors(owner, 1, minimum_error_count=ERROR_BACKOFF_THRESHOLD)
    settings = _make_app_settings(enabled=True).model_copy(
        update={"http_responses_session_bridge_request_budget_seconds": 10.0}
    )
    dashboard = _make_dashboard_settings()
    dashboard.http_responses_session_bridge_request_budget_seconds = 10.0
    _install_proxy_settings(monkeypatch, app_settings=settings, dashboard_settings=dashboard)
    waits = []

    async def advance_wait(**kwargs):
        waits.append(kwargs["sleep_seconds"])
        clock.advance(kwargs["sleep_seconds"])
        if False:
            yield ""

    monkeypatch.setattr(streaming, "_iter_account_capacity_wait_sse", advance_wait)
    response, _ = await _post(async_client, "/v1/responses", [_user("second")], anchor=first_body["id"])
    assert response.status_code == 502, response.text
    assert waits == [10.0]
    assert len(owner_upstream.sent_text) == 1
    assert replacement.sent_text == []


@pytest.mark.asyncio
async def test_independent_equal_unanchored_turns_have_distinct_recordings(
    async_client, recovery_transport, monkeypatch
):
    service, _, _, _, _ = recovery_transport
    upstreams = []

    async def connect(*args, **kwargs):
        upstream = _ClosingBridgeUpstreamWebSocket(f"resp_root_{len(upstreams)}")
        upstreams.append(upstream)
        return upstream

    monkeypatch.setattr(proxy_module, "connect_responses_websocket", connect)
    # Equal request bodies on independent sessions must both be dispatched,
    # even though operation fingerprint lookup spans sessions in one API scope.
    for session_id in ("root-one", "root-two"):
        response, body = await _post(async_client, "/v1/responses", [_user("same")], headers={"session_id": session_id})
        assert response.status_code == 200, response.text
        assert body["id"] == f"resp_root_{len(upstreams) - 1}_1"
    await service.drain_persistence_tasks(timeout_seconds=5)
    assert len(upstreams) == 2
    assert all(len(upstream.sent_text) == 1 for upstream in upstreams)
    async with SessionLocal() as session:
        first = await DurableBridgeRepository(session).get_operation_by_response_id(response_id="resp_root_0_1")
        second = await DurableBridgeRepository(session).get_operation_by_response_id(response_id="resp_root_1_1")
        assert first is not None and second is not None
        assert first.operation_id != second.operation_id
        assert first.request_fingerprint != second.request_fingerprint


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement_allowed", [False, True])
async def test_relocation_preserves_key_account_scope_and_settles_reservations(
    async_client, recovery_transport, monkeypatch, replacement_allowed
):
    service, owner, owner_upstream, replacement, _ = recovery_transport
    created = await async_client.post(
        "/api/api-keys/",
        json={
            "name": "scoped-recovery",
            "assignedAccountIds": [owner.id],
            "limits": [{"limitType": "total_tokens", "limitWindow": "weekly", "maxValue": 100_000}],
        },
    )
    assert created.status_code == 200
    key = created.json()
    assert (await async_client.put("/api/settings", json={"apiKeyAuthEnabled": True})).status_code == 200
    dashboard = _make_dashboard_settings()
    dashboard.api_key_auth_enabled = True
    _install_proxy_settings(monkeypatch, app_settings=_make_app_settings(enabled=True), dashboard_settings=dashboard)
    headers = {"Authorization": f"Bearer {key['key']}"}
    first, first_body = await _post(async_client, "/v1/responses", [_user("first")], headers=headers)
    assert first.status_code == 200
    await service.drain_persistence_tasks(timeout_seconds=5)
    alternate_id = await _import_account(async_client, "scoped-alternate", "scoped-alternate@example.com")
    if replacement_allowed:
        updated = await async_client.patch(
            f"/api/api-keys/{key['id']}", json={"assignedAccountIds": [owner.id, alternate_id]}
        )
        assert updated.status_code == 200
    assert (await async_client.post(f"/api/accounts/{owner.id}/pause")).status_code == 200
    second, _ = await _post(async_client, "/v1/responses", [_user("second")], anchor=first_body["id"], headers=headers)
    assert second.status_code == 200 if replacement_allowed else second.status_code in (502, 503), second.text
    assert len(owner_upstream.sent_text) == 1
    assert len(replacement.sent_text) == int(replacement_allowed)
    await service.drain_persistence_tasks(timeout_seconds=5)
    async with SessionLocal() as session:
        reservations = (
            (
                await session.execute(
                    select(ApiKeyUsageReservation).where(ApiKeyUsageReservation.api_key_id == key["id"])
                )
            )
            .scalars()
            .all()
        )
        assert len(reservations) == 2
        assert all(reservation.status not in ("reserved", "settling") for reservation in reservations)


@pytest.mark.asyncio
async def test_optional_root_recording_failure_preserves_success_and_refuses_incomplete_recovery(
    async_client, recovery_transport, monkeypatch
):
    service, owner, owner_upstream, replacement, _ = recovery_transport
    monkeypatch.setattr(
        service._durable_bridge, "record_operation", AsyncMock(side_effect=RuntimeError("spool unavailable"))
    )
    first, first_body = await _post(async_client, "/v1/responses", [_user("first")])
    assert first.status_code == 200
    await service.drain_persistence_tasks(timeout_seconds=5)
    await _import_account(async_client, "recovery-alternate", "alternate@example.com")
    assert (await async_client.post(f"/api/accounts/{owner.id}/pause")).status_code == 200
    second, _ = await _post(async_client, "/v1/responses", [_user("second")], anchor=first_body["id"])
    assert second.status_code == 502
    assert len(owner_upstream.sent_text) == 1
    assert replacement.sent_text == []
