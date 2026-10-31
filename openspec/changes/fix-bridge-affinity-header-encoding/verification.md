# Local verification

The candidate is for independent review, not automatic publication or deployment.

## Passing gates
- `.venv/bin/pytest -q tests/unit/test_bridge_affinity_transport.py tests/unit/test_http_bridge_forwarding.py tests/unit/test_proxy_http_bridge.py tests/unit/test_proxy_api_responses_contract.py`: **1268 passed**, 1 pre-existing dependency deprecation warning.
- `.venv/bin/pytest -q -n 4 --timeout=120 tests/integration/test_http_responses_bridge.py`: **233 passed**, 4 copies of that warning (one per worker).
- `.venv/bin/pytest -q --timeout=120 tests/integration/test_proxy_websocket_responses.py`: **160 passed**, 1 warning.
- New codec: **100% statement and branch coverage**, 43 transport/security test cases. Two additional parameterized real-route cases verify HMAC, live/durable identity and stripping internal headers before upstream connect.
- `make lint`, `.venv/bin/ty check`, `git diff --check`: pass.
- OpenSpec 1.11.0: strict changed-change validation and strict all-main-spec validation: pass (**68 specs**).
- Old sender, old parser and old session-key reader independently restored from base with an external AST pytest plugin: expected **2 / 2 / 1 regression failures** respectively.
- Six old-receiver compatibility cases: ordinary/literal-`b64:` keys accepted in both modes; encoded keys rejected safely in both modes.

## Broader limitations retained
- A combined bridge + WebSocket run completed with **392 passed, 1 failed**: `test_v1_responses_websocket_reuses_upstream_for_sequential_requests` lacked its second dispatch snapshot. Both the candidate and untouched base pass this test alone. Both also pass the standalone 160-case WebSocket suite. The combined ordering failure is not explained by a passing retry and is not labeled a proven pre-existing failure.
- Full unit/simulation runs exceeded runner limits (exit 143, tool timeout 420s, command timeout 360s). One recorded failure, `tests/unit/test_otel.py::test_lifespan_drains_actual_audit_and_cancelled_fleet_tasks_before_resource_close`, also fails on a complete untouched base archive: audit-route readiness timeout and missing SQLite tables. It was not changed here. No full-unit pass total or full CI success is claimed.
- No production inference, production changes, container build, push, PR, merge or deployment was performed. New encoded-key forwarding needs upgraded receivers; old peers fail closed.

Detailed commands, original RED/GREEN logs and the frozen manifest are outside the repository in the task evidence directory. Independent acceptance and any publication belong to the parent.
