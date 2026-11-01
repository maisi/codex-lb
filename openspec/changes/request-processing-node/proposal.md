# Proposal

## Why
Request history cannot currently identify the replica that executed a request. In a multi-instance bridge deployment the ingress replica can differ from the execution owner, making incident attribution unreliable.

## What Changes
- Persist nullable processing-node provenance with request records and expose `processingNode` in the Request API.
- Reuse the explicitly configured bridge instance identity after safe-label validation; leave default hostnames, unsafe identities and historical records unknown.
- Attribute owner-side execution locally; keep ingress-only forwarding failures unknown rather than inventing an executor.
- Show a concise node label in the existing request list and detail view, with localized Unknown for null or missing fields.
- Add additive migrations for both database lineages without historical rewrites or new indexes.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `proxy-runtime-observability`: persisted execution attribution and nullable Request API contract.
- `responses-api-compat`: bridge ownership and forwarding failure attribution without trusting public metadata.
- `database-migrations`: nullable processing-node column and historical preservation.
- `oracle-database`: additive evolution of the immutable Oracle baseline lineage.
- `frontend-architecture`: compact node display and older-backend compatibility.

## Impact
Request-log model, repository, writer, API mapper/schema, bridge failure handling, Alembic lineages and dashboard request components. No routing, reservation or usage policy changes; no new setting, navigation, dependency or live database requirement.
