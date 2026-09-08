## Context

Fork 5e90f875 and upstream 15ccd901 diverge by 109 and 136 commits respectively, including merge commits. A merge-tree rehearsal finds 34 conflicts. See proposal.md for scope.

## Goals / Non-Goals

Preserve deployed fork contracts while adopting the complete upstream history. Deployment and stable promotion follow verification and beta soak; they are not part of local integration.

## Decisions

Use a real merge so subsequent syncs recognize upstream ancestry. Resolve upstream lifecycle improvements as the baseline and layer only unique fork behavior back in. Preserve migration IDs and add a merge revision. Retain fork publishing permissions and rolling-tag restrictions.

Preserve: bidirectional token vending and borrowed-account background exclusions; per-key ranks over soft process stickiness; opt-in prompt-cache continuation and reports; request-log columns; forced usage; targeted warmup and unplanned resets; reauth telemetry and clipboard fallback. Consolidate bare 404/402 classification on explicit terminal signals. Adopt upstream transport parity while preserving Luna compatibility tests. Upstream prompt-cache owner forwarding complements rather than replaces automatic continuation.

## Risks / Trade-offs

- Clean textual merges can lose semantics: run fork regressions alongside upstream tests.
- Cancellation and reservation ownership can regress: verify public HTTP and websocket failure paths.
- Combined migrations can fork: inspect the graph and exercise existing database upgrades.
- Native transport changes packaging: run native build and frontend/package checks.

## Migration Plan

Back up the database before beta rollout. Upgrade through the combined migration head. Preserve existing fork columns and values. Rollback uses a pre-upgrade backup if the earlier application cannot safely read the upgraded schema. Stable promotion requires the repository beta soak.

## Verified consolidation decisions

Upstream now normalizes non-native HTTP and websocket fingerprints to the same Codex CLI version, originator and user-agent as the fork. Adopt that implementation unchanged and retain the fork Luna regression tests. Retain the fork 404 refresh cooldown alongside upstream nonterminal 404/402 classification. Preserve reauth transition telemetry for both reauth-required and deactivated transitions.

Account state reconstruction stays in the existing fork account_state module to satisfy the architecture ceiling, with upstream clock-driven quota and token-expiry semantics. The facade threads time explicitly and retains the fork health-version fence used by concurrent probe settlement.
