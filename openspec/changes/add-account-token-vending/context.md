# Context

## Problem

OAuth refresh tokens for ChatGPT/Codex rotate on every refresh and OpenAI applies reuse detection: presenting a rotated-out refresh token can invalidate the whole token family. So a single account's refresh token can have exactly **one** rotating owner. Configuring the same account on two independent instances (separate DBs, separate encryption keys) means two owners — they collide on every refresh cycle and bounce the account into `REAUTH_REQUIRED`. This is the dominant cause of "accounts regularly need re-auth" for multi-instance operators who cannot share a database.

## Approach

Access-token vending: one authority owns refresh/rotation; followers fetch short-lived access tokens over HTTPS and never rotate. The refresh token keeps a single owner, so the collision cannot happen.

## Key decisions

- **Single gate at `AuthManager.ensure_fresh`.** Every refresh path funnels through `ensure_fresh` (verified: `refresh_account` is only reachable via `ensure_fresh` → `_run_refresh`). Gating there — reading settings directly — guarantees no rotation path is missed, regardless of which `AuthManager` instance is constructed where.
- **Cross-instance identity = `chatgpt_account_id` (+ `workspace_id`)**, not `account.id`. `account.id` is derived locally and is not stable across instances; `chatgpt_account_id` (from the OAuth id token) is identical for the same ChatGPT account on every instance. The authority resolves via `get_active_by_chatgpt_account_id`.
- **Dedicated shared secret, not the encryption key.** The existing HTTP-bridge HMAC signs with the per-instance `encryption.key`, which followers do not share, and it has no replay protection. Vending uses a separate `account_token_vending_shared_secret` plus a timestamp + nonce in the signature.
- **Re-encrypt on the follower.** The follower returns an `Account` whose `access_token_encrypted` is the vended token encrypted with its own key, so all ~13 downstream proxy call sites that `decrypt(account.access_token_encrypted)` are unchanged. No DB write; the in-memory vend cache provides intra-process warmth.
- **Fail closed via `transport_error`.** Authority-unreachable raises `RefreshError(transport_error=True)`, which the proxy already translates to a transient per-account upstream-unavailable + failover — it does NOT mark the account permanent/`REAUTH_REQUIRED`.

## Operational notes

- Ownership is explicit and per-account. On each instance, list the accounts it *borrows* from a peer in `account_token_vending_remote_accounts` (key = email or chatgpt_account_id, value = peer https base URL); set the same `account_token_vending_shared_secret` everywhere. Accounts not listed are owned/refreshed locally. Both instances can borrow different accounts from each other; an account MUST NOT be borrowed by both sides. `account_token_vending_authority_base_url` remains an optional all-accounts fallback (legacy one-way).
- Each instance that is borrowed *from* must be reachable over HTTPS at its base URL (e.g. its own Cloudflare tunnel hostname scoped to `/internal/bridge/.*`). Bidirectional therefore needs a tunnel per instance.
- Single-owner guard: an instance refuses (`TokenVendNotOwner` → 409) to vend an account it itself borrows, so config drift cannot create a vend loop or a second rotator.
- The `/internal/bridge/*` routes are not behind the public proxy firewall; keep inter-instance traffic on an isolated network / scoped tunnel.
- Reuses the existing internal bridge router and the HMAC pattern from `http_bridge_forwarding.py`; automatic rendezvous/ring ownership is intentionally out of scope (ownership is explicit per the operator's choice).
