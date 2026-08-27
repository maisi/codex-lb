# Account routing — per-API-key account priority

## ADDED Requirements

### Requirement: Per-API-key account priority orders fresh selection

An API key's account assignments SHALL carry an operator-defined rank, and
account selection for that key SHALL prefer the best-ranked account still
eligible to serve the request.

#### Scenario: Preferred account is used while it can still serve

- **WHEN** a key ranks account A above account B and both are eligible
- **THEN** selection returns account A
- **AND** it does so even when account B has substantially lower usage

#### Scenario: Selection falls through when the preferred account cannot serve

- **WHEN** the best-ranked account is rate-limited, quota-exhausted, paused, or
  in error backoff
- **THEN** selection returns the next-best ranked eligible account
- **AND** no additional failover configuration is required

#### Scenario: Priority outranks account routing policy

- **WHEN** the best-ranked account's `routing_policy` is `preserve` and a
  lower-ranked account is `normal`
- **THEN** selection returns the best-ranked account
- **AND** routing policy still orders accounts that share one rank

#### Scenario: Unranked accounts are a last resort

- **WHEN** a key ranks some accounts and is permitted to use others
- **THEN** every ranked eligible account is preferred over any unranked one
- **AND** an unranked account is still selectable once no ranked account is eligible

#### Scenario: Priority does not re-home a pinned conversation

- **WHEN** a request is pinned to a continuity owner
- **THEN** selection resolves to that owner regardless of rank

#### Scenario: Recovery admission is not starved by priority

- **WHEN** a lower-ranked account has a due recovery probe
- **THEN** the recovery admission is chosen before rank narrowing applies

#### Scenario: Keys without ranks are unaffected

- **WHEN** a key has no ranked assignments
- **THEN** selection behaves exactly as it did before priority existed

### Requirement: Ranking is independent of restriction

Assigning and ranking accounts SHALL NOT by itself change which accounts a key
may reach; restriction SHALL remain controlled by
`account_assignment_scope_enabled`.

#### Scenario: Operator ranks without restricting

- **WHEN** an operator supplies ranked assignments and sets
  `account_assignment_scope_enabled` to false
- **THEN** the key prefers the ranked accounts and may still use others

#### Scenario: Default preserves existing behavior

- **WHEN** assignments are supplied without an explicit scope flag
- **THEN** the key is restricted to the assigned accounts, as before
