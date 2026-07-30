## ADDED Requirements

### Requirement: Reports expose provider-reported prompt-cache usage by API key

The Reports API and dashboard SHALL support API-key filtering and grouping over the selected time range and SHALL expose total input tokens, cached input tokens, cache-hit ratio, and daily trends from request-log usage. Cached input MUST be clamped per request to the inclusive range from zero to input tokens, and cache-hit ratio MUST equal cached input divided by total input, or zero when total input is zero.

#### Scenario: Multiple API keys are selected
- **WHEN** an operator filters a report by multiple API keys
- **THEN** summary, daily trends, comparison, and groupings include the union of matching request-log rows

#### Scenario: Cached input is displayed as a subset
- **WHEN** the dashboard renders input and cached-input trends
- **THEN** it clearly labels cached input as included within total input and does not add the two values together

### Requirement: Continuation outcomes are explicit and bounded

The proxy SHALL record continuation attempt, success, skipped, and fallback outcomes with bounded reason labels. It MUST NOT expose avoided prefix items or tokens unless those values are measured reliably for the completed request path.

#### Scenario: Exact continuation succeeds
- **WHEN** an opted-in request is trimmed and accepted as continuation
- **THEN** attempt and success observability increments

#### Scenario: Proof fails or stale anchor falls back
- **WHEN** continuation proof is skipped or an injected anchor falls back to full resend
- **THEN** the corresponding skipped or fallback outcome is recorded with a bounded reason
