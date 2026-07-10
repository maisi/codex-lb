## ADDED Requirements

### Requirement: Non-native Responses requests use a complete Codex CLI identity

When forwarding a non-native Responses request to the ChatGPT Codex upstream over HTTP or websocket, the service MUST replace the inbound identity with a complete Codex CLI fingerprint. The upstream headers MUST contain `originator: codex_cli_rs`, a `version` equal to the current cached Codex client version, and a Codex CLI `User-Agent` built with that same version. The service MUST remove client-supplied `originator`, `version`, and SDK fingerprint headers before applying the normalized identity. Requests identified as native Codex traffic MUST preserve their original identity headers.

#### Scenario: HTTP request cannot select a third-party rollout cohort

- **WHEN** a non-native HTTP Responses request supplies a third-party `originator`, a different `version`, and SDK fingerprint headers
- **THEN** the forwarded request contains the Codex CLI originator, cached Codex version, and matching Codex CLI User-Agent without the third-party identity headers

#### Scenario: Websocket request has the same complete identity

- **WHEN** a non-native Responses websocket request supplies a third-party `originator` or `version`
- **THEN** the upstream websocket handshake contains the Codex CLI originator, cached Codex version, and matching Codex CLI User-Agent

#### Scenario: Native Codex request preserves its own identity

- **WHEN** an inbound Responses request is identified as native Codex traffic
- **THEN** the forwarded request preserves its inbound originator, version, and User-Agent values
