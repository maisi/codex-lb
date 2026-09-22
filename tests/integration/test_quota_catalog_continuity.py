from __future__ import annotations

import json
import time
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import update

import app.core.openai.model_refresh_scheduler as scheduler_module
import app.modules.proxy.service as proxy_module
from app.core.crypto import TokenEncryptor
from app.core.openai.model_registry import ModelRegistry, UpstreamModel, get_model_registry
from app.core.openai.model_registry_store import decode_registry_payload, encode_registry_export
from app.core.utils.time import utcnow
from app.db.models import Account, AccountStatus
from app.db.session import SessionLocal
from app.modules.proxy.account_cache import get_account_selection_cache

pytestmark = pytest.mark.integration


def _account(account_id: str, plan: str) -> Account:
    token = TokenEncryptor().encrypt("test-token")
    return Account(
        id=account_id,
        email=f"{account_id}@example.test",
        plan_type=plan,
        chatgpt_account_id=account_id,
        access_token_encrypted=token,
        refresh_token_encrypted=token,
        id_token_encrypted=token,
        last_refresh=utcnow(),
        status=AccountStatus.ACTIVE,
    )


def _model(plan: str) -> UpstreamModel:
    bootstrap = ModelRegistry(ttl_seconds=60).get_models_with_fallback()["gpt-5.4"]
    return replace(
        bootstrap,
        slug="gpt-6-astra",
        available_in_plans=frozenset({plan}),
        raw={"service_tiers": [{"slug": "priority"}], "additional_speed_tiers": ["priority"]},
    )


def _terminal_response(body: str):
    events = [
        json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ") and line != "data: [DONE]"
    ]
    terminal = [event["response"] for event in events if event["type"] in {"response.failed", "response.completed"}]
    assert len(terminal) == 1, body
    return terminal[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/backend-api/codex/responses", "/v1/responses"])
@pytest.mark.parametrize("status", [AccountStatus.QUOTA_EXCEEDED, AccountStatus.RATE_LIMITED])
async def test_continuation_after_quota_refresh_preserves_owner_policy_and_recovers(
    async_client, monkeypatch, path: str, status: AccountStatus
) -> None:
    owner = _account("catalog-owner", "plus")
    sibling = _account("catalog-sibling", "business")
    async with SessionLocal() as session:
        session.add_all([owner, sibling])
        await session.commit()

    registry = get_model_registry()
    fetched = []
    omit_owner = False

    async def fetch(candidates, encryptor):
        del encryptor
        fetched.extend(account.id for account in candidates)
        models = [] if omit_owner and candidates[0].id == owner.id else [_model(candidates[0].plan_type)]
        return scheduler_module._FetchResult(
            models=models,
            account_models={account.id: (account.plan_type, models) for account in candidates},
        )

    monkeypatch.setattr(scheduler_module, "_fetch_with_failover", fetch)
    scheduler = scheduler_module.ModelRefreshScheduler(interval_seconds=60, enabled=True)
    assert await scheduler._refresh_as_leader()
    assert registry.account_ids_for_model("gpt-6-astra") == frozenset({owner.id, sibling.id})

    async with SessionLocal() as session:
        await session.execute(
            update(Account)
            .where(Account.id == owner.id)
            .values(status=status, reset_at=int(time.time()) + 3600, blocked_at=int(time.time()))
        )
        await session.commit()
    fetched.clear()
    assert await scheduler._refresh_as_leader()
    assert fetched == [sibling.id]

    # Exercise the replica wire representation before using it on the real
    # Responses path. A quota-limited owner must not turn into a policy denial.
    encoded = encode_registry_export(await registry.export_state())
    replica = ModelRegistry(ttl_seconds=60)
    await replica.import_state(
        decode_registry_payload(encoded.payload, refreshed_at=encoded.refreshed_at),
        content_hash=encoded.content_hash,
    )
    await registry.import_state(await replica.export_state(), content_hash=encoded.content_hash)
    monkeypatch.setattr(
        proxy_module.ProxyService, "_resolve_websocket_previous_response_owner", AsyncMock(return_value=owner.id)
    )
    submitted = []

    async def stream(payload, headers, access_token, account_id, **kwargs):
        del headers, access_token, kwargs
        submitted.append(account_id)
        assert account_id == owner.id
        assert payload.previous_response_id == "resp_catalog_owner"
        yield (
            'data: {"type":"response.completed","response":{"id":"resp_catalog_recovered",'
            '"object":"response","status":"completed","output":[],"usage":'
            '{"input_tokens":1,"output_tokens":1,"total_tokens":2}}}\n\n'
        )

    async def ensure_fresh(self, account, **kwargs):
        del self, kwargs
        return account

    monkeypatch.setattr(proxy_module, "core_stream_responses", stream)
    monkeypatch.setattr(proxy_module.ProxyService, "_ensure_fresh_with_budget", ensure_fresh)
    body = {"model": "gpt-6-astra", "input": "continue", "previous_response_id": "resp_catalog_owner", "stream": True}
    response = await async_client.post(path, json=body)
    assert response.status_code == 200, response.text
    assert _terminal_response(response.text)["error"]["code"] == "previous_response_owner_unavailable"
    assert registry.account_ids_for_model("gpt-6-astra") == frozenset({owner.id, sibling.id})
    assert registry.account_ids_for_model_service_tier("gpt-6-astra", "priority") == frozenset({owner.id, sibling.id})
    assert submitted == []

    # Quota recovery needs no further model fetch. The anchored request stays
    # on its owner, even though the sibling had capacity throughout.
    async with SessionLocal() as session:
        await session.execute(
            update(Account)
            .where(Account.id == owner.id)
            .values(status=AccountStatus.ACTIVE, reset_at=None, blocked_at=None)
        )
        await session.commit()
    get_account_selection_cache().invalidate()
    response = await async_client.post(path, json=body)
    assert response.status_code == 200, response.text
    assert _terminal_response(response.text)["id"] == "resp_catalog_recovered"
    assert submitted == [owner.id]
    assert fetched == [sibling.id]

    # A fresh authoritative omission is a genuine policy change. Retained
    # quota-era evidence must not authorize the old model after this refresh.
    omit_owner = True
    assert await scheduler._refresh_as_leader()
    response = await async_client.post(path, json=body)
    assert response.status_code == 200, response.text
    assert _terminal_response(response.text)["error"]["code"] == "previous_response_owner_unavailable"
    assert registry.account_ids_for_model("gpt-6-astra") == frozenset({sibling.id})
    assert submitted == [owner.id]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [AccountStatus.QUOTA_EXCEEDED, AccountStatus.RATE_LIMITED])
async def test_all_accounts_limited_preserves_catalog_without_inventing_unknown_accounts(
    monkeypatch, _reset_db_state, status: AccountStatus
) -> None:
    owner = _account("all-limited-owner", "plus")
    unknown = _account("all-limited-unknown", "plus")
    owner.status = status
    unknown.status = status
    async with SessionLocal() as session:
        session.add_all([owner, unknown])
        await session.commit()

    registry = get_model_registry()
    models = [_model("plus")]
    await registry.update(
        {"plus": models},
        per_account_results={owner.id: ("plus", models)},
        active_account_plans={owner.id: "plus"},
    )
    fetch = AsyncMock(side_effect=AssertionError("capacity-limited accounts must not be fetched"))
    monkeypatch.setattr(scheduler_module, "_fetch_with_failover", fetch)
    scheduler = scheduler_module.ModelRefreshScheduler(interval_seconds=60, enabled=True)
    assert await scheduler._refresh_as_leader()
    fetch.assert_not_awaited()
    snapshot = registry.get_snapshot()
    assert snapshot is not None
    assert snapshot.account_plans == {owner.id: "plus"}
    assert registry.account_ids_for_model("gpt-6-astra") == frozenset({owner.id})
    assert registry.account_ids_for_model_service_tier("gpt-6-astra", "priority") == frozenset({owner.id})
