from __future__ import annotations

import time
from types import SimpleNamespace
from typing import cast

import pytest
from pydantic import ValidationError

from app.core.auth.refresh import RefreshError
from app.core.config.settings import Settings
from app.core.crypto import TokenEncryptor
from app.core.utils.time import utcnow
from app.db.models import Account, AccountStatus
from app.modules.accounts import auth_manager as auth_manager_module
from app.modules.accounts.auth_manager import AccountsRepositoryPort, AuthManager
from app.modules.accounts.token_vending import (
    VEND_NONCE_HEADER,
    VEND_SIGNATURE_HEADER,
    VEND_TIMESTAMP_HEADER,
    VendTokenRequest,
    VendTokenResponse,
    build_vend_signature,
    canonical_request_body,
    verify_vend_signature,
)

pytestmark = pytest.mark.unit

_SECRET = b"shared-vend-secret"


def _signed_headers(request: VendTokenRequest, *, timestamp: str, nonce: str = "abc123") -> dict[str, str]:
    body = canonical_request_body(request)
    sig = build_vend_signature(timestamp=timestamp, nonce=nonce, body_json=body, secret=_SECRET)
    return {VEND_TIMESTAMP_HEADER: timestamp, VEND_NONCE_HEADER: nonce, VEND_SIGNATURE_HEADER: sig}


def test_vend_signature_roundtrips() -> None:
    request = VendTokenRequest(chatgpt_account_id="cg-1", workspace_id="ws-1")
    now = time.time()
    headers = _signed_headers(request, timestamp=repr(now))
    assert verify_vend_signature(headers, body_json=canonical_request_body(request), secret=_SECRET, now=now) is None


def test_vend_signature_rejects_tampered_body() -> None:
    request = VendTokenRequest(chatgpt_account_id="cg-1")
    now = time.time()
    headers = _signed_headers(request, timestamp=repr(now))
    tampered = canonical_request_body(VendTokenRequest(chatgpt_account_id="cg-EVIL"))
    assert verify_vend_signature(headers, body_json=tampered, secret=_SECRET, now=now) is not None


def test_vend_signature_rejects_wrong_secret() -> None:
    request = VendTokenRequest(chatgpt_account_id="cg-1")
    now = time.time()
    headers = _signed_headers(request, timestamp=repr(now))
    result = verify_vend_signature(headers, body_json=canonical_request_body(request), secret=b"other", now=now)
    assert result is not None


def test_vend_signature_rejects_replay_outside_skew() -> None:
    request = VendTokenRequest(chatgpt_account_id="cg-1")
    signed_at = 1_000_000.0
    headers = _signed_headers(request, timestamp=repr(signed_at))
    # "now" is 10 minutes after the request was signed -> outside the 30s window.
    result = verify_vend_signature(
        headers,
        body_json=canonical_request_body(request),
        secret=_SECRET,
        now=signed_at + 600,
    )
    assert result is not None and "replay" in result.lower()


def test_vend_signature_rejects_missing_headers() -> None:
    request = VendTokenRequest(chatgpt_account_id="cg-1")
    assert verify_vend_signature({}, body_json=canonical_request_body(request), secret=_SECRET) is not None


def test_settings_requires_https_authority_and_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(
            account_token_vending_authority_base_url="http://authority:2455",
            account_token_vending_shared_secret="s",
        )
    with pytest.raises(ValidationError):
        Settings(account_token_vending_authority_base_url="https://authority:2455")  # secret missing
    ok = Settings(
        account_token_vending_authority_base_url="https://authority:2455",
        account_token_vending_shared_secret="s",
    )
    assert ok.account_token_vending_authority_base_url == "https://authority:2455"


class _RecordingRepo:
    def __init__(self) -> None:
        self.status_updates: list[tuple[str, AccountStatus]] = []
        self.token_updates = 0

    async def get_by_id(self, account_id: str) -> Account | None:
        return None

    async def update_status(self, account_id, status, deactivation_reason=None, reset_at=None, blocked_at=None) -> bool:
        self.status_updates.append((account_id, status))
        return True

    async def update_tokens(self, *args, **kwargs) -> bool:
        self.token_updates += 1
        return True

    async def workspace_slot_taken(self, **kwargs) -> bool:
        return False


def _follower_account() -> tuple[Account, TokenEncryptor]:
    encryptor = TokenEncryptor()
    account = Account(
        id="acc-follower",
        chatgpt_account_id="cg-shared",
        email="user@example.com",
        plan_type="plus",
        access_token_encrypted=encryptor.encrypt("OLD-ACCESS"),
        refresh_token_encrypted=encryptor.encrypt("REFRESH-MUST-NOT-CHANGE"),
        id_token_encrypted=encryptor.encrypt("ID-MUST-NOT-CHANGE"),
        last_refresh=utcnow(),
        status=AccountStatus.ACTIVE,
        deactivation_reason=None,
    )
    return account, encryptor


@pytest.mark.asyncio
async def test_follower_ensure_fresh_vends_without_rotating(monkeypatch: pytest.MonkeyPatch) -> None:
    auth_manager_module._clear_refresh_singleflight_state()
    monkeypatch.setattr(
        auth_manager_module,
        "get_settings",
        lambda: SimpleNamespace(account_token_vending_authority_base_url="https://authority:2455"),
    )

    def _explode(*_a: object, **_k: object):
        raise AssertionError("follower must not rotate the refresh token")

    monkeypatch.setattr(auth_manager_module, "refresh_access_token", _explode)

    async def _fake_vend(account, *, force, authority_base_url):
        assert authority_base_url == "https://authority:2455"
        return VendTokenResponse(access_token="VENDED-ACCESS", expires_at_ms=0, account_id="cg-shared", plan_type="pro")

    monkeypatch.setattr(auth_manager_module, "vend_follower_access_token", _fake_vend)

    account, encryptor = _follower_account()
    original_refresh = account.refresh_token_encrypted
    original_id = account.id_token_encrypted
    repo = _RecordingRepo()
    manager = AuthManager(cast(AccountsRepositoryPort, repo))

    result = await manager.ensure_fresh(account, force=True)

    assert encryptor.decrypt(result.access_token_encrypted) == "VENDED-ACCESS"
    assert result.refresh_token_encrypted == original_refresh  # never rotated
    assert result.id_token_encrypted == original_id
    assert repo.token_updates == 0  # follower does not persist
    assert repo.status_updates == []


@pytest.mark.asyncio
async def test_follower_fails_closed_without_reauth(monkeypatch: pytest.MonkeyPatch) -> None:
    auth_manager_module._clear_refresh_singleflight_state()
    monkeypatch.setattr(
        auth_manager_module,
        "get_settings",
        lambda: SimpleNamespace(account_token_vending_authority_base_url="https://authority:2455"),
    )

    async def _vend_unavailable(account, *, force, authority_base_url):
        raise RefreshError("vend_unavailable", "authority unreachable", False, transport_error=True)

    monkeypatch.setattr(auth_manager_module, "vend_follower_access_token", _vend_unavailable)

    account, _ = _follower_account()
    repo = _RecordingRepo()
    manager = AuthManager(cast(AccountsRepositoryPort, repo))

    with pytest.raises(RefreshError) as exc_info:
        await manager.ensure_fresh(account, force=True)

    assert exc_info.value.transport_error is True
    assert exc_info.value.is_permanent is False
    assert repo.status_updates == []  # never marked REAUTH_REQUIRED
