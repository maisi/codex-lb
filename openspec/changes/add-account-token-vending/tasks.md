# Tasks

## 1. Settings
- [x] 1.1 Add `account_token_vending_remote_accounts` (explicit per-account borrow list, key=url) / `_authority_base_url` (optional fallback) / `_shared_secret` / `_access_token_skew_seconds` (env prefix `CODEX_LB_`).
- [x] 1.2 Parse the borrow list (`key=url`, comma-separated, `NoDecode`); model-validate every vend URL is `https://` with a hostname and the shared secret is present when any is configured.
- [x] 1.3 Document the settings in `.env.example`.

## 2. Vending module (`app/modules/accounts/token_vending.py`)
- [x] 2.1 `VendTokenRequest` / `VendTokenResponse` models; `canonical_request_body` (deterministic JSON for signing on both sides).
- [x] 2.2 `build_vend_signature` / `verify_vend_signature` — HMAC-SHA256 over `METHOD|PATH|timestamp|nonce|sha256(body)` with timestamp-skew rejection (replay).
- [x] 2.3 `AccountTokenVendingClient` — per-account cache to `exp - skew`, re-vend on force; HTTPS POST with signed headers; fail closed as `RefreshError(transport_error=True)` on any non-200/transport/parse failure.

## 3. Per-account gate (`AuthManager.ensure_fresh`)
- [x] 3.1 Resolve `vend_authority_for_account` (borrow list by email/chatgpt_account_id, else fallback URL). If set, vend and return an account with a re-encrypted access token; never rotate, never write refresh/id tokens, never persist. Gate sits ahead of the singleflight so all rotation paths are covered.

## 4. Authority endpoint
- [x] 4.1 `ProxyService.vend_access_token` — resolve account by `chatgpt_account_id` (fallback `account_id`); refuse with `TokenVendNotOwner` if this instance itself borrows it (single-owner guard); else refresh via the normal singleflighted path and return only access token + expiry + identity.
- [x] 4.2 `POST /internal/bridge/oauth-token` — verify HMAC signature, 503 if unconfigured, 403 on bad/expired signature, 409 if not the owner, 404 on unknown account, else the vend response.

## 4a. Loopback-secured transport + lazy background vend
- [x] 4a.1 Allow `http://` for local hosts (loopback / RFC1918-private / link-local / `localhost` / `host.docker.internal`) in vending-URL validation, so the owner can be reached via an SSH tunnel / local terminator / docker-bridge relay; `http://` to a public address still rejected.
- [x] 4a.2 Add `ensure_fresh(..., background=False)`; borrowed accounts are NOT vended on background passes (auth guardian, usage refresh, model refresh, limit warm-up all pass `background=True`) — only on the live request path. Owned accounts unaffected.

## 5. Tests
- [ ] 5.1 Signing round-trips; tampered body/expired timestamp/missing headers are rejected.
- [ ] 5.2 Follower `ensure_fresh` vends and NEVER calls `refresh_access_token` / mutates refresh/id tokens; authority-unreachable fails closed (transport error) without REAUTH.
- [ ] 5.3 HTTPS-only + shared-secret-required settings validation.

## 6. Validate
- [ ] 6.1 `uv run ruff check` + `uv run pytest` (auth manager, token vending, settings).
- [ ] 6.2 `openspec validate add-account-token-vending --strict`.
