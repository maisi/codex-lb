## Why

The same ChatGPT account can be configured on more than one codex-lb instance that do NOT share a database (no shared SQL, no shared encryption key). OAuth refresh tokens rotate on every refresh with reuse detection, so each independent holder invalidates the other's refresh token and the account is forced into `REAUTH_REQUIRED` — repeatedly, regardless of how the account was logged in. A shared database (e.g. an SSH-tunnelled Postgres) is operationally undesirable.

## What Changes

- Introduce inter-instance **access-token vending** over HTTPS: each account has exactly one **owner** (it alone refreshes/rotates); other instances **borrow** it and fetch short-lived **access** tokens from the owner and never call OpenAI's `/oauth/token`. Ownership is explicit and per-account, so two instances can borrow different accounts from each other (bidirectional) without auto-sharing the whole pool.
- Add settings: `account_token_vending_remote_accounts` (explicit borrow list, key=email-or-chatgpt_account_id → owner https URL), `account_token_vending_authority_base_url` (optional all-accounts fallback / legacy one-way), `account_token_vending_shared_secret` (dedicated HMAC secret, independent of the encryption key), `account_token_vending_access_token_skew_seconds`.
- Guard the authority endpoint so an instance refuses to vend an account it itself borrows (single-owner invariant; prevents vend loops under config drift).
- Add an authenticated, HTTPS-only authority endpoint `POST /internal/bridge/oauth-token` that returns only `{access_token, expires_at_ms, account_id, plan_type}` — never the refresh or id token.
- Gate refresh inside `AuthManager.ensure_fresh`: in follower mode it vends (cached per account until shortly before access-token expiry, re-vending on force/401) and returns an account whose `access_token_encrypted` is the vended token re-encrypted with the follower's own key, so all downstream callers are unchanged. This single gate covers every rotation path (proxy, usage updater, auth guardian, probe, model refresh, warmup).
- Authenticate vend requests with HMAC-SHA256 over a canonical request string including a timestamp + nonce (replay resistance); enforce `https://` for the authority URL; never log token material.

## Impact

- New capability `account-token-vending`. Default-off: with the authority URL unset, behavior is identical to today.
- Files: `app/core/config/settings.py`, `app/modules/accounts/token_vending.py` (new), `app/modules/accounts/auth_manager.py`, `app/modules/proxy/service.py`, `app/modules/proxy/api.py`, `.env.example`.
- Security surface: a short-lived access token crosses the wire (TLS), authenticated by a shared HMAC secret; refresh/id tokens never leave the authority. The `/internal/bridge/*` routes are not behind the public proxy firewall, so network isolation between instances is still required.
- Adds unit coverage for signing/replay/verification, the HTTPS-only settings validator, and the follower-never-rotates gate.
