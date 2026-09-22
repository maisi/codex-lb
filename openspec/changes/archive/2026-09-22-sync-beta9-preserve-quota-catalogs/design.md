## Context

The deployed fork is based on beta6 with additional routing and continuity fixes. Its model refresh uses the immediately active account set both for fetching catalogs and deciding whether prior capability evidence survives. Temporary quota state can therefore become an authoritative model-policy refusal.

## Goals / Non-Goals

Goals are a single beta9 integration, preservation of fork behavior, compatible migrations, and stable model capability knowledge across temporary quota/rate-limit states. This change does not authorize sending account-bound history to a sibling or retain capability evidence after genuine administrative removal or plan changes.

## Decisions

- Merge the exact upstream prerelease tag and retain ancestry. Resolve fork deltas semantically rather than replacing the fork with an upstream snapshot.
- Separate accounts eligible for upstream catalog fetch from accounts whose last-known capabilities remain valid. Continue fetching only active accounts; retain existing evidence for rate-limited and quota-exhausted accounts with the same plan. Unknown accounts remain unknown, and fresh authoritative omissions supersede retained evidence.
- Reuse the registry's existing stale-account retention and persisted snapshot representation where possible. Avoid a new cache, setting, or routing bypass.
- Add forward-only Alembic merge revisions if needed; preserve all deployed revision identifiers. Test upgrades with representative fork account assignments and policies.

## Risks / Trade-offs

- Retaining capabilities must not grant quota or bypass file, API-key, security, plan, or service-tier constraints. Verify request-facing selection and genuine removal cases.
- All-accounts-exhausted refreshes must preserve valid prior evidence without inventing fresh discovery or capabilities for unseen accounts.
- Imported migrations and fork schema branches can introduce multiple heads. Inspect the combined graph and upgrade populated databases before readiness.
- The upstream release changes dashboard behavior; retain fork UI controls and attach before/after evidence where applicable.

## Migration Plan

Validate locally and through GitHub CI, merge the combined integration only after all gates pass, then let the fork image pipeline publish the combined code. Production rollback requires the pre-upgrade database backup if the previous binary is incompatible with imported schema changes.
