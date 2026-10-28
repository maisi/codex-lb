# Tasks

## 1. Separate load from quota

- [x] 1.1 Keep observed quota in AccountState and compose dimensionless local-load discounts with draw weights; verify state, disabled-weight, and weighted-selector regression tests.
- [x] 1.2 Exercise concurrent proxy requests and routing trace reads before, during, and after lease release; verify quota values, preferred tier, unknown windows, and task cleanup through integration tests.

## 2. Synchronize contracts and verification

- [x] 2.1 Correct existing quota-window explanations in all locales and sync the affected OpenSpec requirements/context; verify the routing settings test and scoped spec validation.
- [x] 2.2 Run relevant routing, trace, lease-lifecycle, lint/type checks and OpenSpec validation; record verification evidence and inspect the final diff.

## Workflow follow-up

- Verify implementation against these artifacts, then archive this change and its synced specs.
