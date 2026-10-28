"""The dashboard can read back why a proxy request was routed to its account."""

from __future__ import annotations

import pytest

import app.modules.proxy.load_balancer as load_balancer_module
import app.modules.proxy.service as proxy_module
from app.core.openai.models import OpenAIResponsePayload
from app.modules.proxy.routing_trace import get_routing_trace_store
from tests.integration.test_api_keys_api import _TEST_MODELS, _import_account, _populate_test_registry

pytestmark = pytest.mark.integration


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
