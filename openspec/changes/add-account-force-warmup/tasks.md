## 1. Targeted Backend Warmup

- [ ] 1.1 Add a one-account compact warmup service entry point that preserves logging, credential vending, transport handling, and accounting exclusions
- [ ] 1.2 Add the dashboard-authenticated account warmup endpoint with active-status validation and a structured result schema
- [ ] 1.3 Add route-level regressions for authorization, selected-account isolation, inactive and missing accounts, success, structured failure, and borrowed-account token vending

## 2. Accounts Page Action

- [ ] 2.1 Add the account warmup API client, response schema, and mutation hook with affected-query invalidation
- [ ] 2.2 Add the immediate `Warm now` action with active, read-only, and pending-state guards while preserving `Force probe`
- [ ] 2.3 Add localized success and failure feedback and update API mocks
- [ ] 2.4 Add Accounts page product-path tests for success, structured failure, HTTP failure, duplicate suppression, and action eligibility

## 3. Verification

- [ ] 3.1 Run focused backend and frontend tests for targeted account warmup
- [ ] 3.2 Run lint, type checks, architecture checks, and strict OpenSpec validation
- [ ] 3.3 Run the full backend and frontend test suites and review the final diff
