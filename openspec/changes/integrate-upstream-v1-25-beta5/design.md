## Context

The fork main at `042cdca1` integrated beta.4. Upstream advanced to `5794d8d7`, including a beta.5 release and settings promotions. Several upstream edits overlap helpers extracted by the fork.

## Decisions

Use a merge commit to retain upstream ancestry. Resolve overlaps at the function level: bring upstream account-health fixes into the fork's extracted account-state module, retain ranked selection and seed precedence, preserve vending and continuation hooks, and adopt upstream helper consolidation. Keep upstream's dedicated release-guard workflow with the fork's official tag-provenance fetch.

Add an operation-free Alembic merge revision joining the previous fork merge and upstream dashboard-timeout head. Preserve existing revision identities and verify upgrades from both histories with existing account/key rows.

## Risks

Conflicts can silently discard upstream behavior or fork features. Validate routing, bridge lifecycle, migration data, settings references, native transports, and dashboard regressions. The imported upstream release metadata is provenance-checked; it does not authorize publishing a fork release.
