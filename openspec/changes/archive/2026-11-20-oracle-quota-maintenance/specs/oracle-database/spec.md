## ADDED Requirements

### Requirement: Oracle quota maintenance
The service SHALL monitor the finite schema quota of the bridge tablespace on Oracle. It SHALL show a dashboard warning below 3 GiB, permit operators with operations write access to request maintenance, and attempt maintenance without dashboard traffic strictly below 2 GiB. SQLite, PostgreSQL and unlimited quotas SHALL produce no quota warning or maintenance DDL.

#### Scenario: Manual warning range
- **WHEN** available quota is at least 2 GiB and below 3 GiB
- **THEN** the dashboard shows remaining quota and offers a maintenance action to authorized operators

#### Scenario: Critical quota
- **WHEN** available quota falls below 2 GiB
- **THEN** an independent worker initiates maintenance, serializing attempts across replicas and backing off after unsuccessful attempts

#### Scenario: Online recovery
- **WHEN** eligible bridge segments have reclaimable space and sufficient working space
- **THEN** the worker uses targeted online maintenance, preserves transcript rows, constraints and retention, and rechecks quota

#### Scenario: Insufficient space or failure
- **WHEN** an attempt cannot safely recover space or a database operation fails
- **THEN** the dashboard exposes the outcome and the service continues monitoring

#### Scenario: Other backends
- **WHEN** another supported database backend is in use
- **THEN** the application runs no Oracle maintenance queries or worker and displays no Oracle controls
