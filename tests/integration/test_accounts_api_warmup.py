from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest

import app.modules.accounts.auth_manager as auth_manager_module
import app.modules.proxy.service as proxy_module
from app.core.auth import generate_unique_account_id
from app.core.openai.models import CompactResponsePayload
from app.modules.accounts.token_vending import VendTokenResponse
from app.modules.proxy.service import ProxyService, WarmupAccountResultData

pytestmark = pytest.mark.integration


def _encode_jwt(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    body = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    return f"header.{body}.sig"


async def _import_account(async_client, *, account_id: str, email: str, workspace_id: str | None = None) -> str:
    payload = {
        "email": email,
        "chatgpt_account_id": account_id,
        "https://api.openai.com/auth": {
            "chatgpt_plan_type": "plus",
            "chatgpt_workspace_id": workspace_id,
        },
    }
    auth_json = {
        "tokens": {
            "idToken": _encode_jwt(payload),
            "accessToken": "access-token",
            "refreshToken": "refresh-token",
            "accountId": account_id,
        },
    }
    response = await async_client.post(
        "/api/accounts/import",
        files={"auth_json": ("auth.json", json.dumps(auth_json), "application/json")},
    )
    assert response.status_code == 200, response.text
    return generate_unique_account_id(account_id, email, workspace_id)


@pytest.mark.asyncio
async def test_targeted_warmup_missing_account_returns_404(async_client, monkeypatch):
    async def _fail_warmup(*_args, **_kwargs):
        raise AssertionError("missing account must not invoke warmup")

    monkeypatch.setattr(ProxyService, "warmup_account", _fail_warmup)
    response = await async_client.post("/api/accounts/missing/warmup")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "account_not_found"


@pytest.mark.asyncio
async def test_targeted_warmup_rejects_inactive_account(async_client, monkeypatch):
    async def _fail_warmup(*_args, **_kwargs):
        raise AssertionError("inactive account must not invoke warmup")

    monkeypatch.setattr(ProxyService, "warmup_account", _fail_warmup)
    account_id = await _import_account(
        async_client,
        account_id="acc-warmup-paused",
        email="warmup-paused@example.com",
    )
    pause_response = await async_client.post(f"/api/accounts/{account_id}/pause")
    assert pause_response.status_code == 200

    response = await async_client.post(f"/api/accounts/{account_id}/warmup")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "account_not_warmable"


@pytest.mark.asyncio
async def test_targeted_warmup_submits_only_selected_account(async_client, monkeypatch):
    selected_id = await _import_account(
        async_client,
        account_id="acc-warmup-selected",
        email="warmup-selected@example.com",
    )
    await _import_account(
        async_client,
        account_id="acc-warmup-other",
        email="warmup-other@example.com",
    )
    seen: list[str] = []

    async def _fake_warmup(self, *, account, headers):  # noqa: ARG001
        seen.append(account.id)
        assert "cookie" not in headers
        return WarmupAccountResultData(
            account_id=account.id,
            success=True,
            request_id="resp-selected",
            model="gpt-5.4-mini",
        )

    monkeypatch.setattr(ProxyService, "warmup_account", _fake_warmup)

    response = await async_client.post(
        f"/api/accounts/{selected_id}/warmup",
        headers={"Cookie": "dashboard_session=must-not-forward"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "accountId": selected_id,
        "success": True,
        "requestId": "resp-selected",
        "model": "gpt-5.4-mini",
        "errorCode": None,
        "errorMessage": None,
    }
    assert seen == [selected_id]


@pytest.mark.asyncio
async def test_targeted_warmup_returns_structured_failure(async_client, monkeypatch):
    account_id = await _import_account(
        async_client,
        account_id="acc-warmup-failure",
        email="warmup-failure@example.com",
    )

    async def _fake_warmup(self, *, account, headers):  # noqa: ARG001
        return WarmupAccountResultData(
            account_id=account.id,
            success=False,
            request_id="req-failed",
            model="gpt-5.4-mini",
            error_code="upstream_unavailable",
            error_message="owner unavailable",
        )

    monkeypatch.setattr(ProxyService, "warmup_account", _fake_warmup)

    response = await async_client.post(f"/api/accounts/{account_id}/warmup")

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["errorCode"] == "upstream_unavailable"
    assert response.json()["errorMessage"] == "owner unavailable"


@pytest.mark.asyncio
async def test_targeted_warmup_vends_borrowed_account_token(async_client, monkeypatch):
    workspace_id = "workspace-borrowed"
    account_id = await _import_account(
        async_client,
        account_id="acc-warmup-borrowed",
        email="warmup-borrowed@example.com",
        workspace_id=workspace_id,
    )
    monkeypatch.setattr(
        auth_manager_module,
        "get_settings",
        lambda: SimpleNamespace(
            account_token_vending_remote_accounts={"warmup-borrowed@example.com": "https://owner.example"},
            account_token_vending_authority_base_url=None,
        ),
    )
    seen: dict[str, object] = {}

    async def _fake_vend(account, *, force, authority_base_url):
        seen["workspace_id"] = account.workspace_id
        seen["force"] = force
        seen["authority"] = authority_base_url
        return VendTokenResponse(
            access_token="vended-warmup-token",
            expires_at_ms=0,
            account_id=account.chatgpt_account_id,
            plan_type=account.plan_type,
        )

    async def _fake_compact(payload, headers, access_token, account_id, **kwargs):  # noqa: ARG001
        seen["access_token"] = access_token
        return CompactResponsePayload.model_validate(
            {
                "object": "response.compact",
                "id": "resp-borrowed",
                "status": "completed",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        )

    monkeypatch.setattr(auth_manager_module, "vend_follower_access_token", _fake_vend)
    monkeypatch.setattr(proxy_module, "core_compact_responses", _fake_compact)

    response = await async_client.post(f"/api/accounts/{account_id}/warmup")

    assert response.status_code == 200, response.text
    assert response.json()["success"] is True, response.text
    assert seen == {
        "workspace_id": workspace_id,
        "force": False,
        "authority": "https://owner.example",
        "access_token": "vended-warmup-token",
    }
