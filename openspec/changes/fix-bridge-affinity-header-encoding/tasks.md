## 1. Reproduce and specify
- [x] 1.1 Preserve deterministic RED on actual generated thread key and bridge product path.
- [x] 1.2 Audit all raw-header consumers, signatures, public-header gates and upstream state.
## 2. Implement and cover
- [x] 2.1 Implement narrow lossless transport and shared strict decoder with independent TDD slices.
- [x] 2.2 Cover both signature modes, literal legacy keys, malformed/ambiguous/tampered input, unsafe metadata and public isolation.
## 3. Verify
Independent parent review remains required. This is a frozen local candidate, not a claim of clean full CI. The broad combined integration run had an order-sensitive WebSocket failure; separate bridge and WebSocket suites pass. A full-unit lifespan failure reproduces on the untouched base. Full-unit runs were interrupted, so no full-unit total is asserted. Keep this change active until independent acceptance.

- [x] 3.1 Run focused/broad offline tests and sabotage old functions to prove regression sensitivity.
- [x] 3.2 Run Ruff, type, architecture and strict OpenSpec validation; disclose unrelated baseline failures.
- [x] 3.3 Freeze local candidate with manifest and German evidence report for independent parent acceptance; no publication.
