## 1. Fix and reproduce

- [x] 1.1 Add real-socket readiness regressions for equivalent close tokens, keep-alive and declined upgrades.
- [x] 1.2 Honor the parser's close decision in the httptools adapter.

## 2. Verify

- [x] 2.1 Run focused socket, upgrade, timer, disconnect and CLI checks and strict OpenSpec validation.
- [x] 2.2 Trial the minimal patch reversibly against the incident and record observed results.
- [x] 2.3 Verify and sync the requirement/context, then archive the completed change.
