## ADDED Requirements

### Requirement: Follower instances never rotate refresh tokens

When `account_token_vending_authority_base_url` is configured, the instance is a follower and MUST obtain account access tokens by vending them from the authority over HTTPS. A follower MUST NOT call OpenAI's token endpoint and MUST NOT mutate the stored refresh token or id token for any account. The follower gate MUST cover every path that would otherwise refresh a token (proxy request freshness, usage refresh, auth guardian, account probe, model refresh, warmup).

#### Scenario: follower serves traffic without rotating

- **GIVEN** the authority base URL is configured on a follower
- **WHEN** any subsystem requests a fresh token for an account
- **THEN** the follower fetches a short-lived access token from the authority
- **AND** it does not call OpenAI's `/oauth/token`
- **AND** the account's stored refresh and id tokens are left unchanged

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
