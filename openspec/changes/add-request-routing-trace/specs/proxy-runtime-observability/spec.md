# Proxy runtime observability — per-request routing traces

## ADDED Requirements

### Requirement: Account selection decisions are explainable per request

Every proxy account selection made for a request SHALL record a routing trace
containing the selection outcome (`kept_owner`, `moved_from_owner`,
`new_selection`, `required_account` or `no_account`), the selected account, the
API key priority rank that served a fresh selection, the selector pass that
decided, and every candidate account with its key rank, routing policy, status,
health, primary and secondary usage, whether it exceeded the budget threshold,
and the reason it could not serve. Accounts ranked by the API key that were not
offered to the selector SHALL be listed separately. Recording a trace SHALL NOT
change which account is selected, and a failure while recording SHALL NOT fail
the request.

Traces SHALL be kept only in a bounded per-process memory store and SHALL be
logged once per selection, with account identifiers redacted when the request's
privacy policy redacts sensitive details. `GET /api/request-logs/{request_id}/routing`
SHALL return the traces recorded for that request id, oldest first, and an empty
list when none are kept, and SHALL require the `accounts:write` permission.

#### Scenario: A tier failover is explained

- **GIVEN** an API key with tiers `[[A, B], [C]]` and account A unavailable
- **WHEN** a request with that key is routed to account B
- **THEN** the request's routing trace reports outcome `new_selection`,
  selected account B and serving rank 0
- **AND** lists account C with rank 1

#### Scenario: A budget-threshold move to the next tier is distinguishable

- **GIVEN** an API key with tiers `[[A, B], [C]]`, account A rate-limited and
  account B above the budget threshold
- **WHEN** account C is selected
- **THEN** the trace reports serving rank 1
- **AND** marks account B as eligible and over the budget threshold
- **AND** marks account A as unavailable because it is rate-limited

#### Scenario: Unknown requests return no traces

- **WHEN** the routing traces of a request id the process has no record of are requested
- **THEN** the response lists no attempts

#### Scenario: Traces require account identity permission

- **WHEN** a dashboard principal without `accounts:write` requests a routing trace
- **THEN** the request is rejected
