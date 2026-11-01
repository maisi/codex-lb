# Design

## Context
See proposal.md and context.md. Request persistence is centralized, while bridge execution can occur on another replica. The default bridge ID is derived from socket hostname.

## Goals / Non-Goals
Persist execution identity without changing routing or settlement. Avoid host inventory exposure, historical inference, new database sessions, public attribution headers and new settings.

## Decisions
- Resolve safe explicit identity from base Settings.model_fields_set, a narrow ASCII label grammar and recognized credential-prefix exclusions. Request-bound dashboard overlays do not define instance identity. Resolve at the execution writer before detaching persistence; do not derive on API reads.
- Owner-side logs naturally use the owner's configuration. Suppress local attribution for ingress handoff failures through explicit server-side failure provenance; successful remote forwarding does not produce a duplicate origin row. Preserve local attribution when recovery actually runs locally.
- Store String(64), nullable, without default/index, and expose the field with a null default in Python and optional nullable frontend schema. Show the label in existing row metadata and details.
- Keep the Oracle baseline immutable; evolve its dedicated Alembic lineage and expected snapshot used by transfer validation.

## Risks / Trade-offs
- Operators can explicitly choose a sensitive label → narrow grammar and documentation reduce inadvertent disclosure; never consult host inventory for public identity.
- Failed handoffs can have ambiguous dispatch → null is preferable to guessing; execution-owner rows remain authoritative.
- Oracle DDL is not transactional → use the project's restartable additive schema pattern and offline tests; no live readiness claim.

## Migration Plan
Add one descendant revision per existing lineage. Test upgrade/downgrade and historical null preservation on disposable SQLite plus offline Oracle schema/migration compatibility. Parent handles deployment and migration ordering after independent review.
