## 1. Implementation

- [x] 1.1 Make the byte-budgeted queue generic over its item size function
- [x] 1.2 Bound native websocket messages at 4096 messages and 32 MiB
- [x] 1.3 Regression test: a 500-frame burst reaches a late consumer intact
- [x] 1.4 Keep the overflow path named `consumer_backpressure`

## 2. Verification

- [x] 2.1 Lint, type check and affected test modules
- [x] 2.2 Strict OpenSpec validation
