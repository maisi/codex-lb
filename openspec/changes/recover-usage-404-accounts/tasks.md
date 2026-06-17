## 1. Spec And Regression Coverage

- [x] 1.1 Add OpenSpec deltas for usage 404 handling and Accounts page probe recovery.
- [x] 1.2 Add usage-refresh coverage proving plain usage 404 does not deactivate accounts.
- [x] 1.3 Add account probe coverage proving usage-404-deactivated accounts can recover on successful probe.
- [x] 1.4 Add frontend action coverage proving Force probe is enabled only for recoverable deactivated accounts.

## 2. Implementation

- [x] 2.1 Change usage-refresh classification so HTTP 404 alone is not a deactivation signal.
- [x] 2.2 Allow backend probe for usage-404-deactivated accounts and reactivate on successful upstream status.
- [x] 2.3 Expose `deactivationReason` to the frontend account schema and update Force probe disablement.

## 3. Verification

- [x] 3.1 Run focused backend and frontend tests for the touched paths.
- [ ] 3.2 Run OpenSpec validation if the CLI is available in the environment.
