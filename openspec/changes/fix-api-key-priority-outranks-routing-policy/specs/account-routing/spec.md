# Account routing — per-API-key priority on the proxy selection path

## ADDED Requirements

### Requirement: Per-API-key account priority holds on every fresh-selection path

Fresh account selection for an API key with ranked account assignments SHALL
determine the serving rank before applying `burn_first` / `normal` / `preserve`
preference or the sticky reallocation budget preference, on every proxy
selection path. Routing policy and budget preference SHALL only order accounts
within the serving rank. The serving rank SHALL be the best rank among eligible
accounts below the sticky reallocation budget threshold, or the best rank among
all eligible accounts when none below the threshold can serve. A due recovery
probe SHALL still be admitted before rank is applied.

#### Scenario: Lower-ranked burn_first account does not jump the queue

- **GIVEN** an API key ranks account A above account B
- **AND** account A has routing policy `normal` and account B has `burn_first`
- **AND** both accounts are eligible and below the budget threshold
- **WHEN** a request with that key needs a fresh account selection
- **THEN** account A is selected

#### Scenario: Top-ranked preserve account still serves

- **GIVEN** an API key ranks account A above account B
- **AND** account A has routing policy `preserve` and account B has `normal`
- **AND** both accounts are eligible and below the budget threshold
- **WHEN** a request with that key needs a fresh account selection
- **THEN** account A is selected

#### Scenario: Crossing the budget threshold moves traffic down one rank

- **GIVEN** an API key ranks account A above account B
- **AND** account A is above the sticky reallocation budget threshold
- **AND** account B is eligible and below it, whatever its routing policy
- **WHEN** a request with that key needs a fresh account selection
- **THEN** account B is selected

#### Scenario: Rank order returns when every rank is over the threshold

- **GIVEN** an API key ranks account A above account B
- **AND** both accounts are eligible and above the budget threshold
- **AND** account B has routing policy `burn_first`
- **WHEN** a request with that key needs a fresh account selection
- **THEN** account A is selected

#### Scenario: Routing policy still orders accounts that share a rank

- **GIVEN** no ranked account of an API key can serve
- **AND** the key may use unranked accounts C (`normal`) and D (`burn_first`)
- **WHEN** a request with that key needs a fresh account selection
- **THEN** account D is selected
