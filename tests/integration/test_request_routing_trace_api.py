"""The dashboard can read back why a proxy request was routed to its account."""

from __future__ import annotations

import asyncio
import json
from datetime import timezone

import pytest

import app.modules.proxy.load_balancer as load_balancer_module
import app.modules.proxy.service as proxy_module
from app.core.openai.models import OpenAIResponsePayload
from app.core.utils.request_id import get_request_id
from app.core.utils.time import utcnow
from app.db.session import SessionLocal
from app.modules.proxy.routing_trace import get_routing_trace_store
from app.modules.usage.repository import UsageRepository
from tests.integration.test_api_keys_api import _TEST_MODELS, _import_account, _populate_test_registry

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
@pytest.mark.parametrize("primary_used", [8.0, None])
@pytest.mark.parametrize("route", ["/v1/responses", "/backend-api/codex/responses", "/v1/responses/compact"])
async def test_concurrent_proxy_requests_keep_observed_quota_and_burn_first_tier(
    async_client, app_instance, monkeypatch, primary_used, route
):
    await _populate_test_registry()
    get_routing_trace_store().clear()
    monkeypatch.setattr(
        load_balancer_module,
        "_filter_accounts_for_model",
        lambda accounts, model, *, service_tier=None: accounts,
    )
    accounts = {}
    for name, policy in (("normal", "normal"), ("burn", "burn_first"), ("reserve", "preserve")):
        accounts[name] = await _import_account(async_client, f"acc-load-{name}", f"{name}@example.com")
        update = await async_client.put(
            f"/api/accounts/{accounts[name]}/routing-policy", json={"routingPolicy": policy}
        )
        assert update.status_code == 200
    now = int(utcnow().replace(tzinfo=timezone.utc).timestamp())
    async with SessionLocal() as session:
        usage = UsageRepository(session)
        for name, primary, secondary in (("normal", 85.0, 27.0), ("burn", primary_used, 15.0), ("reserve", 0.0, 17.0)):
            if primary is not None:
                await usage.add_entry(
                    account_id=accounts[name],
                    window="primary",
                    used_percent=primary,
                    reset_at=now + 3600,
                    window_minutes=300,
                )
            await usage.add_entry(
                account_id=accounts[name],
                window="secondary",
                used_percent=secondary,
                reset_at=now + 7200,
                window_minutes=10080,
            )
    settings = await async_client.put(
        "/api/settings",
        json={"stickyThreadsEnabled": False, "preferEarlierResetAccounts": False, "apiKeyAuthEnabled": True},
    )
    assert settings.status_code == 200
    create = await async_client.post(
        "/api/api-keys/",
        json={
            "name": "load-key",
            "assignedAccountTiers": [[accounts["normal"], accounts["burn"]], [accounts["reserve"]]],
        },
    )
    assert create.status_code == 200
    key = create.json()["key"]
    upstream_started = asyncio.Event()
    release_upstream = asyncio.Event()

    async def fake_compact(payload, headers, access_token, account_id):
        del headers, access_token, account_id
        if payload.instructions.startswith("hold:"):
            upstream_started.set()
            await release_upstream.wait()
        return OpenAIResponsePayload.model_validate({"output": []})

    monkeypatch.setattr(proxy_module, "core_compact_responses", fake_compact)

    async def fake_stream(payload, headers, access_token, account_id, **_kwargs):
        await fake_compact(payload, headers, access_token, account_id)
        event = {"type": "response.completed", "response": {"id": f"resp_{get_request_id()}", "output": []}}
        yield f"data: {json.dumps(event)}\n\n"

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    async def request(request_id, *, hold=False):
        body = {"model": _TEST_MODELS[0], "instructions": "hold:" + "x" * 8192 if hold else "hi", "input": []}
        if not route.endswith("/compact"):
            body["stream"] = True
        return await async_client.post(
            route,
            headers={"Authorization": f"Bearer {key}", "x-request-id": request_id},
            json=body,
        )

    assert (await request("load-before")).status_code == 200
    balancer = app_instance.state.proxy_service._load_balancer
    pending = asyncio.create_task(request("load-held", hold=True))
    try:
        await asyncio.wait_for(upstream_started.wait(), timeout=10)
        create_count, stream_count, tokens = await balancer.account_pressure_snapshot(accounts["burn"])
        assert create_count + stream_count > 0
        assert tokens > 7560  # The old token/credit calculation saturated both windows.
        assert (await asyncio.wait_for(request("load-during"), timeout=10)).status_code == 200
        release_upstream.set()
        assert (await asyncio.wait_for(pending, timeout=10)).status_code == 200
    finally:
        release_upstream.set()
        if not pending.done():
            pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
    assert (await request("load-after")).status_code == 200
    assert await balancer.account_pressure_snapshot(accounts["burn"]) == (0, 0, 0.0)

    for request_id in ("load-before", "load-during", "load-after"):
        response = await async_client.get(f"/api/request-logs/{request_id}/routing")
        assert response.status_code == 200
        [attempt] = response.json()["attempts"]
        assert attempt["selectedAccountId"] == accounts["burn"]
        assert attempt["servingRank"] == 0
        burn = next(candidate for candidate in attempt["candidates"] if candidate["accountId"] == accounts["burn"])
        assert burn["primaryUsedPercent"] == primary_used
        assert burn["secondaryUsedPercent"] == 15.0
        assert burn["overBudgetThreshold"] is False


@pytest.mark.asyncio
async def test_request_routing_trace_explains_a_tier_failover(async_client, monkeypatch):
    await _populate_test_registry()
    get_routing_trace_store().clear()
    monkeypatch.setattr(
        load_balancer_module,
        "_filter_accounts_for_model",
        lambda accounts, model, *, service_tier=None: accounts,
    )
    policies = {"acc-trace-first": "burn_first", "acc-trace-second": "normal", "acc-trace-reserve": "burn_first"}
    account_ids: dict[str, str] = {}
    for chatgpt_id, policy in policies.items():
        account_ids[chatgpt_id] = await _import_account(async_client, chatgpt_id, f"{chatgpt_id}@example.com")
        assert (
            await async_client.put(
                f"/api/accounts/{account_ids[chatgpt_id]}/routing-policy",
                json={"routingPolicy": policy},
            )
        ).status_code == 200
    # The top account of the shared tier is out, so its tier-mate must serve.
    assert (await async_client.post(f"/api/accounts/{account_ids['acc-trace-first']}/pause")).status_code == 200

    settings = await async_client.put(
        "/api/settings",
        json={
            "stickyThreadsEnabled": False,
            "preferEarlierResetAccounts": False,
            "totpRequiredOnLogin": False,
            "apiKeyAuthEnabled": True,
        },
    )
    assert settings.status_code == 200
    create = await async_client.post(
        "/api/api-keys/",
        json={
            "name": "traced-key",
            "assignedAccountTiers": [
                [account_ids["acc-trace-first"], account_ids["acc-trace-second"]],
                [account_ids["acc-trace-reserve"]],
            ],
        },
    )
    assert create.status_code == 200
    key = create.json()["key"]

    async def fake_compact(payload, headers, access_token, account_id):
        del payload, headers, access_token, account_id
        return OpenAIResponsePayload.model_validate({"output": []})

    monkeypatch.setattr(proxy_module, "core_compact_responses", fake_compact)
    response = await async_client.post(
        "/backend-api/codex/responses/compact",
        headers={"Authorization": f"Bearer {key}", "x-request-id": "routing-trace-req-1"},
        json={"model": _TEST_MODELS[0], "instructions": "hi", "input": []},
    )
    assert response.status_code == 200
    request_id = response.headers["x-request-id"]

    routing = await async_client.get(f"/api/request-logs/{request_id}/routing")

    assert routing.status_code == 200
    body = routing.json()
    assert body["requestId"] == request_id
    [attempt] = body["attempts"]
    assert attempt["outcome"] == "new_selection"
    assert attempt["selectedAccountId"] == account_ids["acc-trace-second"]
    assert attempt["servingRank"] == 0
    assert attempt["keyRanksAccounts"] is True
    assert attempt["rankedAccountsNotOffered"] == [account_ids["acc-trace-first"]]
    candidates = {candidate["accountId"]: candidate for candidate in attempt["candidates"]}
    assert candidates[account_ids["acc-trace-second"]]["rank"] == 0
    assert candidates[account_ids["acc-trace-second"]]["eligible"] is True
    assert candidates[account_ids["acc-trace-reserve"]]["rank"] == 1
    assert candidates[account_ids["acc-trace-reserve"]]["routingPolicy"] == "burn_first"


@pytest.mark.asyncio
async def test_request_routing_trace_is_empty_for_unknown_requests(async_client):
    response = await async_client.get("/api/request-logs/never-seen-request/routing")

    assert response.status_code == 200
    assert response.json() == {"requestId": "never-seen-request", "attempts": []}
