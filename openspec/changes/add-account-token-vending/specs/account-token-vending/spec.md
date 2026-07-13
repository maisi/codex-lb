## ADDED Requirements

### Requirement: Each account has a single rotating owner; borrowers never rotate

Account ownership MUST be resolved per account: an account is *borrowed* when it appears in this instance's explicit borrow list (`account_token_vending_remote_accounts`, keyed by email or chatgpt_account_id), or when the all-accounts fallback `account_token_vending_authority_base_url` is set; otherwise it is owned and refreshed locally. For a borrowed account the instance MUST obtain access tokens by vending from the named peer over HTTPS, MUST NOT call OpenAI's token endpoint, and MUST NOT mutate the stored refresh or id token. The gate MUST cover every path that would otherwise refresh a token (proxy request freshness, usage refresh, auth guardian, account probe, model refresh, warmup). Two instances MAY each borrow different accounts from the other (bidirectional), provided no account is borrowed by both sides.

#### Scenario: borrowed account serves traffic without rotating

- **GIVEN** an account listed in this instance's borrow list
- **WHEN** any subsystem requests a fresh token for it
- **THEN** the instance fetches a short-lived access token from the named peer
- **AND** it does not call OpenAI's `/oauth/token`
- **AND** the account's stored refresh and id tokens are left unchanged

#### Scenario: locally owned account is refreshed normally

- **GIVEN** an account NOT in this instance's borrow list (and no all-accounts fallback configured)
- **WHEN** a fresh token is needed
- **THEN** the instance refreshes/rotates it locally as usual and does not vend it

#### Scenario: an instance refuses to vend an account it borrows

- **WHEN** a vend request reaches an instance for an account that this instance itself borrows from a peer
- **THEN** the instance refuses (does not refresh or rotate it) so the single-owner invariant holds and no vend loop occurs

#### Scenario: follower caches the vended token

- **WHEN** a borrowing instance has a cached access token that is not yet within the configured expiry skew
- **THEN** it reuses the cached token without contacting the peer
- **AND** a forced refresh (e.g. after an upstream 401) bypasses the cache and re-vends

#### Scenario: follower caches the vended token

- **WHEN** a follower has a cached access token that is not yet within the configured expiry skew
- **THEN** it reuses the cached token without contacting the authority
- **AND** a forced refresh (e.g. after an upstream 401) bypasses the cache and re-vends

### Requirement: Authority vends only short-lived access tokens

The authority endpoint MUST authenticate the request, resolve the account through its normal rotation-safe refresh path, and return only the access token, its expiry, and non-secret identity metadata (account id, plan type). It MUST NOT return the refresh token or id token.

#### Scenario: authority returns an access token for a known account

- **WHEN** a correctly signed vend request arrives for an account known to the authority
- **THEN** the authority refreshes the account through its singleflighted refresh path
- **AND** responds with the access token, expiry, account id, and plan type only

#### Scenario: unknown account is rejected without a token

- **WHEN** a signed vend request names an account the authority does not have
- **THEN** the authority returns a not-found error and no token

### Requirement: Vend requests are authenticated, replay-resistant, and HTTPS-only

Vend requests MUST be authenticated with an HMAC-SHA256 signature over a canonical request string that includes a timestamp and a nonce, keyed by a shared secret distinct from the encryption key. Requests with a missing/invalid signature MUST be rejected, and requests whose timestamp falls outside the allowed skew MUST be rejected as possible replays. The authority base URL MUST be an `https://` URL, validated at startup.

#### Scenario: invalid or replayed signature is rejected

- **WHEN** a vend request has a missing, tampered, or wrong-secret signature
- **OR** its timestamp is outside the allowed skew window
- **THEN** the authority rejects it without returning a token

#### Scenario: non-HTTPS authority URL fails startup validation

- **WHEN** `account_token_vending_authority_base_url` is set to a non-`https` URL or has no host, or the shared secret is missing
- **THEN** configuration validation fails at startup

### Requirement: Followers fail closed without rotating

When the authority is unreachable, a follower MUST continue to serve a cached access token while it is still valid, and once no valid token is available it MUST surface a transient per-account upstream-unavailable error rather than rotating the refresh token or marking the account `REAUTH_REQUIRED`.

#### Scenario: authority outage does not cause re-auth

- **GIVEN** a follower whose cached access token has expired
- **WHEN** the authority is unreachable
- **THEN** the follower returns a transient per-account failure
- **AND** it does not rotate the refresh token
- **AND** it does not drive the account to `REAUTH_REQUIRED`

### Requirement: Token material is never logged

Neither the follower nor the authority may log access, refresh, or id token values when vending.

### Requirement: Vending URLs are HTTPS, except a local host over a secured channel

Configured vending URLs (`account_token_vending_authority_base_url` and every value in `account_token_vending_remote_accounts`) MUST use `https://`, EXCEPT `http://` is permitted when the host is local: a loopback address, a private (RFC1918) or link-local address, or `localhost`/`host.docker.internal`. This exists so the owner endpoint can be reached over a hop that already carries its own transport security — an SSH tunnel, a co-located TLS terminator, or a docker-bridge relay. `http://` to a public address MUST fail configuration validation at startup.

#### Scenario: http to a local host is accepted; public http is rejected

- **WHEN** a borrow-list entry points at `http://` a loopback / private / link-local address or `host.docker.internal` (e.g. a docker-bridge relay or SSH-tunnelled owner endpoint)
- **THEN** configuration validation accepts it
- **AND** an `http://` URL to a public address is rejected at startup

### Requirement: Borrowed accounts are vended lazily, only on the live request path

Background/maintenance passes (auth guardian, usage refresh, model refresh, limit warm-up) MUST NOT vend a borrowed account; they leave it untouched so no request reaches the owner (e.g. an on-demand SSH tunnel to the owner stays idle). A borrowed account is vended only when the live proxy request path selects it.

#### Scenario: background pass does not reach the owner for a borrowed account

- **WHEN** a background scheduler processes a borrowed account
- **THEN** it does not vend the account and does not contact the owner
- **AND** the account is vended only when a live request selects it

#### Scenario: background usage refresh never re-auths a borrowed account

- **GIVEN** a borrowed account whose last vended access token has expired
- **WHEN** any background scheduler processes it (usage refresh, limit warm-up, reset-credits refresh, or model refresh)
- **THEN** it skips the account rather than calling upstream with the stale access token
- **AND** even if an upstream call returns 401/token_expired for a borrowed account, the follower MUST NOT mark it `REAUTH_REQUIRED` (the refresh token is owned by the peer, so the failure is transient, not an account-level auth failure)
