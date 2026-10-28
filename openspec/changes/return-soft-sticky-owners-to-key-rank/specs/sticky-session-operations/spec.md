# sticky-session-operations — soft owners yield to preserve and key rank

## ADDED Requirements

### Requirement: Soft sticky owners yield to preserve semantics and a cold return to key rank

Before a soft `prompt_cache`, `sticky_thread` or `codex_session` owner keeps
its conversation, selection SHALL determine the account a new conversation
would get under the same ranking, routing-policy and budget rules, without
admitting a recovery probe. The owner SHALL be released and the mapping
rebound to the account selection then chooses when either:

- the owner's routing policy is `preserve` and that account is a different,
  non-`preserve` account; or
- the API key ranks accounts, the conversation has not been used for at least
  600 seconds, and that account holds a better rank than the owner.

The last use SHALL be the mapping's `updated_at` on TTL-based kinds. A mapping
without a known last use SHALL count as warm. Routing strategies
`sequential_drain`, `reset_drain` and `single_account`, a mapping preserved on
fallback, and owners resolved from hard continuity sources
(`previous_response_id`, turn state, live or durable bridge ownership, file
pins) SHALL NOT be released by this rule. Routing traces SHALL record the
release as owner flag `preserve_release` or `rank_return`.

#### Scenario: A preserve owner hands its conversation back

- **GIVEN** a prompt-cache conversation pinned to a healthy `preserve` account
- **AND** a `normal` account that a new conversation would get
- **WHEN** the next turn is routed
- **THEN** it is served by the `normal` account and the mapping points to it
- **AND** the trace's owner flags include `preserve_release`

#### Scenario: A preserve owner on the key's best rank keeps its conversation

- **GIVEN** a key that ranks a `preserve` account first and a `normal` account second
- **WHEN** the next turn of a conversation pinned to the `preserve` account is routed
- **THEN** it stays on the `preserve` account

#### Scenario: A cold conversation returns to the key's better rank

- **GIVEN** a key ranking account A above account B
- **AND** a prompt-cache conversation pinned to B, last used 11 minutes ago
- **AND** A can serve
- **WHEN** the next turn is routed
- **THEN** it is served by A and the mapping points to A
- **AND** the trace's owner flags include `rank_return`

#### Scenario: A warm conversation keeps its account

- **GIVEN** the same key and a conversation pinned to B, last used 2 minutes ago
- **WHEN** the next turn is routed
- **THEN** it stays on B
