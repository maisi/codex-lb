## Verification

Completeness: 6/6 tasks complete. Both changed requirements are implemented and exactly synced to the main spec. Correctness and coherence checks found no outstanding issues.

| Contract | Evidence |
| --- | --- |
| Positive pre-dispatch evidence and one bounded retry | Real native adapters in `test_native_send_adapter_preserves_only_positive_pre_dispatch_evidence` and bridge submit regressions |
| Successful, exhausted and ambiguous retry outcomes | `test_http_bridge_submit_closed_native_socket_retries_once_and_settles`, including an ambiguous second send and unused/used half-open probe ownership |
| Same-account and file-owner constraints | Reconnect pin assertions and `test_http_bridge_closed_native_retry_cannot_send_on_a_replacement_account` |
| Reattach cannot revive a resource-close owner | `test_http_bridge_reattach_cannot_revive_a_resource_close_owner`, before and during replacement connect |
| Local, native and signed internal error envelopes | `test_http_bridge_native_send_failure_returns_retryable_envelope`, before/after commit and with/without prewarm under thread affinity |
| Owner-to-origin provenance | Forwarding unit coverage and `test_native_codex_owner_forward_handled_failure_returns_502_before_commit` |

## Validation results

- `make lint`: passed, including architecture, cancellation, timing, settings and migration topology checks.
- `uv run --extra oracle ty check`: passed.
- Eight affected modules: 1,592 passed (`test_proxy_http_bridge`, `test_http_bridge_forwarding`, `test_proxy_websocket_client`, `test_native_egress`, `test_http_bridge_cancel_drain`, `test_http_bridge_relay_loop`, `test_http_responses_bridge`, `test_multi_instance_bridge`).
- After the prewarm correction, both complete bridge modules were rerun: 1,349 passed. The final retry/account-fence matrix passed separately: 5 passed.
- Existing API Responses contracts and streaming timeout hardening: 98 passed.
- `npx --yes @fission-ai/openspec@1.11.0 validate fix-http-bridge-closed-send --strict`: passed.
- `npx --yes @fission-ai/openspec@1.11.0 validate --specs --strict`: 68 passed. Main/delta requirement blocks also compared equal.

## Limits

The original production socket-close chronology and deployed replica behavior were not independently inspected. Reproductions use real Python native adapters with stubbed helper commands and in-process ASGI routes. No running container or server was accessed; no deployment, push or PR is part of this change.
