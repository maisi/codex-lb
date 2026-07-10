"""Inter-instance access-token vending.

When the same ChatGPT account is configured on more than one codex-lb instance
that do NOT share a database, each instance independently rotates the OAuth
refresh token. OpenAI rotates refresh tokens on every refresh with reuse
detection, so two independent holders invalidate each other and the account
falls into ``REAUTH_REQUIRED``.

This module lets ONE instance act as the token *authority* (it alone refreshes
and rotates) while other instances are *followers* that fetch short-lived
*access* tokens from the authority over HTTPS and never call OpenAI's
``/oauth/token``. The refresh token therefore has a single rotating owner and
the collision cannot occur.

Security: requests are authenticated with an HMAC-SHA256 signature over a
canonical request string that includes a timestamp and a random nonce (replay
resistance), keyed by a dedicated shared secret -- NOT the per-instance
encryption key, which followers do not share. Only the access token (plus its
expiry and non-secret identity metadata) ever crosses the wire; the refresh and
id tokens never leave the authority. Vended tokens are never logged.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time

import aiohttp
from pydantic import BaseModel

from app.core.auth import token_expiry_epoch_ms
from app.core.auth.refresh import RefreshError
from app.core.config.settings import get_settings
from app.core.utils.request_id import get_request_id

logger = logging.getLogger(__name__)

VEND_PATH = "/internal/bridge/oauth-token"
VEND_METHOD = "POST"
VEND_TIMESTAMP_HEADER = "x-codex-vend-timestamp"
VEND_NONCE_HEADER = "x-codex-vend-nonce"
VEND_SIGNATURE_HEADER = "x-codex-vend-signature"

_DEFAULT_MAX_SKEW_SECONDS = 30.0
_DEFAULT_VEND_TIMEOUT_SECONDS = 10.0


class VendTokenRequest(BaseModel):
    chatgpt_account_id: str | None = None
    workspace_id: str | None = None
    account_id: str | None = None


class VendTokenResponse(BaseModel):
    access_token: str
    expires_at_ms: int
    account_id: str | None = None
    plan_type: str | None = None


def canonical_request_body(payload: VendTokenRequest) -> str:
    """Deterministic JSON used on BOTH sides so the body digest matches."""
    return json.dumps(
        payload.model_dump(mode="json", exclude_none=True),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _signing_secret() -> bytes:
    secret = get_settings().account_token_vending_shared_secret
    if not secret:
        raise RefreshError(
            "vend_misconfigured",
            "account_token_vending_shared_secret is not configured",
            False,
            transport_error=True,
        )
    return secret.encode("utf-8")


def build_vend_signature(*, timestamp: str, nonce: str, body_json: str, secret: bytes) -> str:
    body_digest = hashlib.sha256(body_json.encode("utf-8")).hexdigest()
    signing_payload = "|".join((VEND_METHOD, VEND_PATH, timestamp, nonce, body_digest))
    return hmac.new(secret, signing_payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_vend_signature(
    headers,
    *,
    body_json: str,
    secret: bytes,
    max_skew_seconds: float = _DEFAULT_MAX_SKEW_SECONDS,
    now: float | None = None,
) -> str | None:
    """Return an error reason string if the signed request is invalid, else None."""
    timestamp = (headers.get(VEND_TIMESTAMP_HEADER) or "").strip()
    nonce = (headers.get(VEND_NONCE_HEADER) or "").strip()
    signature = (headers.get(VEND_SIGNATURE_HEADER) or "").strip()
    if not timestamp or not nonce or not signature:
        return "missing vend signature headers"
    try:
        sent_at = float(timestamp)
    except ValueError:
        return "invalid vend timestamp"
    current = time.time() if now is None else now
    if abs(current - sent_at) > max_skew_seconds:
        return "vend timestamp outside allowed skew (possible replay)"
    expected = build_vend_signature(timestamp=timestamp, nonce=nonce, body_json=body_json, secret=secret)
    if not hmac.compare_digest(signature, expected):
        return "invalid vend signature"
    return None


class _CachedVend:
    __slots__ = ("response", "expires_at_ms")

    def __init__(self, response: VendTokenResponse, expires_at_ms: int) -> None:
        self.response = response
        self.expires_at_ms = expires_at_ms


class AccountTokenVendingClient:
    """Follower-side client that fetches access tokens from the authority.

    Caches the vended token per account until shortly before its expiry so a
    follower hits the authority at most once per access-token lifetime. The
    authority's own refresh singleflight coalesces concurrent demand into a
    single real ``/oauth/token`` rotation.
    """

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], _CachedVend] = {}

    @staticmethod
    def _cache_key(request: VendTokenRequest) -> tuple[str, str]:
        return (request.chatgpt_account_id or request.account_id or "", request.workspace_id or "")

    def _skew_ms(self) -> int:
        return int(max(0.0, get_settings().account_token_vending_access_token_skew_seconds) * 1000)

    def clear(self) -> None:
        self._cache.clear()

    async def vend(self, request: VendTokenRequest, *, authority_base_url: str, force: bool) -> VendTokenResponse:
        key = self._cache_key(request)
        now_ms = int(time.time() * 1000)
        if not force:
            cached = self._cache.get(key)
            if cached is not None and now_ms < cached.expires_at_ms - self._skew_ms():
                return cached.response
        response = await self._fetch(request, authority_base_url=authority_base_url)
        # Prefer the JWT's own exp; fall back to the authority-reported expiry.
        expires_at_ms = token_expiry_epoch_ms(response.access_token) or response.expires_at_ms
        self._cache[key] = _CachedVend(response, expires_at_ms)
        return response

    async def _fetch(self, request: VendTokenRequest, *, authority_base_url: str) -> VendTokenResponse:
        body_json = canonical_request_body(request)
        timestamp = repr(time.time())
        nonce = secrets.token_hex(16)
        signature = build_vend_signature(
            timestamp=timestamp,
            nonce=nonce,
            body_json=body_json,
            secret=_signing_secret(),
        )
        headers = {
            "content-type": "application/json",
            VEND_TIMESTAMP_HEADER: timestamp,
            VEND_NONCE_HEADER: nonce,
            VEND_SIGNATURE_HEADER: signature,
        }
        request_id = get_request_id()
        if request_id:
            headers["x-request-id"] = request_id
        url = f"{authority_base_url.rstrip('/')}{VEND_PATH}"
        timeout = aiohttp.ClientTimeout(total=_DEFAULT_VEND_TIMEOUT_SECONDS)
        try:
            async with aiohttp.ClientSession(trust_env=False) as session:
                async with session.post(url, data=body_json, headers=headers, timeout=timeout) as resp:
                    if resp.status != 200:
                        detail = (await resp.text())[:200]
                        logger.warning(
                            "Token vend failed account=%s status=%s request_id=%s",
                            request.chatgpt_account_id or request.account_id,
                            resp.status,
                            request_id,
                        )
                        raise RefreshError(
                            "vend_unavailable",
                            f"Token vend failed ({resp.status}): {detail}",
                            False,
                            transport_error=True,
                        )
                    data = await resp.json(content_type=None)
        except RefreshError:
            raise
        except (aiohttp.ClientError, TimeoutError, OSError) as exc:
            raise RefreshError(
                "vend_unavailable",
                f"Token vend transport error: {exc or exc.__class__.__name__}",
                False,
                transport_error=True,
            ) from exc
        try:
            return VendTokenResponse.model_validate(data)
        except Exception as exc:
            raise RefreshError(
                "vend_unavailable",
                "Token vend response invalid",
                False,
                transport_error=True,
            ) from exc


_VENDING_CLIENT = AccountTokenVendingClient()


def get_account_token_vending_client() -> AccountTokenVendingClient:
    return _VENDING_CLIENT


class TokenVendNotOwner(Exception):
    """Raised on the authority side when a vend request targets an account that
    THIS instance itself borrows from a peer -- i.e. this instance is not the
    owner and must not refresh it (prevents A->B->A vend loops and protects the
    single-owner invariant under config drift)."""


def vend_authority_for_account(account, settings) -> str | None:
    """Return the peer base URL this instance should vend the account's access
    token from, or ``None`` when this instance owns/refreshes the account
    locally.

    Explicit per-account borrow list (``account_token_vending_remote_accounts``),
    keyed by email or ``chatgpt_account_id``, takes precedence. The instance-wide
    ``account_token_vending_authority_base_url`` is an optional all-accounts
    fallback (legacy one-way mode); leave it unset for explicit per-account
    ownership.
    """
    remote = getattr(settings, "account_token_vending_remote_accounts", None) or {}
    if remote:
        for key in (getattr(account, "email", None), getattr(account, "chatgpt_account_id", None)):
            if key and key in remote:
                return remote[key]
    return getattr(settings, "account_token_vending_authority_base_url", None)


async def vend_follower_access_token(account, *, force: bool, authority_base_url: str) -> VendTokenResponse:
    request = VendTokenRequest(
        chatgpt_account_id=account.chatgpt_account_id,
        workspace_id=account.workspace_id,
        account_id=account.id,
    )
    return await _VENDING_CLIENT.vend(request, authority_base_url=authority_base_url, force=force)


def _clear_token_vending_cache() -> None:
    _VENDING_CLIENT.clear()
