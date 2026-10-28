## ADDED Requirements

### Requirement: Local load does not alter quota observations

The proxy MUST keep normalized upstream quota percentages independent of
in-flight requests and reserved tokens. Quota-based sticky release and API-key
priority-tier selection MUST compare those quota observations with their
configured thresholds. Local load MUST NOT alone cause a quota-threshold move
to a lower priority tier or a preserve account.

#### Scenario: Concurrent work does not exhaust an available burn-first account

- **GIVEN** an API key ranks two available Plus accounts ahead of a preserve account
- **AND** the burn-first Plus account reports 8% primary and 15% secondary usage
- **AND** another request holds a lease reserving 160000 tokens on that account
- **WHEN** another foreground request selects an account
- **THEN** the burn-first account remains below the quota threshold
- **AND** traffic does not move to the preserve tier solely because of the lease

#### Scenario: Actual quota pressure still moves traffic

- **GIVEN** every selectable account in the first priority tier exceeds the configured quota threshold
- **AND** an account in the next tier remains below the threshold
- **WHEN** the proxy selects an account
- **THEN** quota-based tier fallback remains available

### Requirement: Local load discounts weighted selection independently

Weighted account selection MUST apply local load as a nonnegative draw-weight
discount independent of quota percentages. In-flight pressure MUST use the
configured percentage per lease. Token pressure MUST normalize reserved tokens
per million tokens before applying the configured token weight. Releasing a
lease MUST remove its load contribution without changing observed quota.

#### Scenario: Large token reservations remain a bounded weight adjustment

- **GIVEN** one stream reserves 160000 tokens with the default in-flight penalty of 2.5 and token weight of 1
- **WHEN** weighted selection evaluates its account
- **THEN** its existing draw-weight multiplier is divided by 1.185
- **AND** its primary and secondary quota percentages are unchanged

#### Scenario: Disabled load weights retain other weighting

- **GIVEN** both local load weights are zero
- **WHEN** an account has active leases
- **THEN** its existing error-rate and latency weighting remains unchanged
