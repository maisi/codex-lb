## ADDED Requirements

### Requirement: Account auth-status transitions are observable

When the runtime flips an account to a non-routable auth status (`REAUTH_REQUIRED` or `DEACTIVATED`), it MUST emit a structured `WARNING` log and increment a Prometheus counter. The diagnostics MUST include the account id, the target status, the upstream error code that caused the flip, the originating source subsystem, and the age of the account's last credential refresh at the moment of the flip. The counter MUST use only low-cardinality labels (target status, bounded upstream error code, and source). The diagnostics MUST NOT include token material.

#### Scenario: token-refresh permanent failure is observable

- **WHEN** a background or request-driven token refresh fails permanently and flips the account to `REAUTH_REQUIRED`
- **THEN** the runtime logs the account id, status, upstream error code, a `token_refresh` source, and the last-refresh age
- **AND** it increments the account status-transition counter with the matching `status`, `error_code`, and `source` labels
- **AND** the log does not contain access, refresh, or id token values

#### Scenario: proxy and usage paths are attributed to distinct sources

- **WHEN** the proxy data path marks an account as a permanent failure
- **OR** the usage-refresh path deactivates an account for a client error
- **THEN** the emitted counter and log carry a `proxy` or `usage_refresh` source label respectively, so operators can attribute the flip to the originating subsystem

#### Scenario: race-recovery does not record a false transition

- **WHEN** a token refresh observes a permanent error but the stored refresh token has already changed (a concurrent refresh won the rotation)
- **THEN** the runtime returns the latest account without flipping it
- **AND** no account status-transition diagnostic or counter increment is emitted for that account
