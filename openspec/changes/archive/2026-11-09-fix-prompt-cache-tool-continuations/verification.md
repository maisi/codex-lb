## Verification

Verified on 2026-11-09 before archive. No critical, warning, or coherence findings remain.

### Completeness and correctness

- All implementation tasks are complete. Both new requirements and the modified denied-anchor requirement are implemented; main specs and stable context are synced.
- `test_prompt_cache_continuation_preserves_full_request_after_tool_call_completion` drives function, custom, and apply-patch response completion through the bridge, then submits the next full request and checks the actual upstream frame. The unanswered tool call remains outside the stored request-input prefix, demonstrating why prefix equality alone was insufficient.
- `test_prompt_cache_continuation_skips_replayed_tool_suffix_without_local_manifest` covers all eight supported tool-call/output item types without relying on a local pending manifest. Existing message-only continuation coverage still passes.
- `test_prompt_cache_missing_tool_output_recovery_at_bridge` exercises real pre-created retry dispatch and successful replacement completion, sanitized client-anchor failure, refusal of unsafe/non-neutral/concurrent replay, and termination of a second anonymous rejection. Successful recovery emits no corruption rewrite, failure status, error-health write, or spurious reconnect request; terminal finalization occurs once.
- `test_denied_prompt_cache_anchor_is_retired_before_fresh_replay_and_next_submit` covers both upstream denial classes, successful and failed replay sends, and enabled/disabled continuation on the following submit. It verifies durable owner-fenced retirement before replay mutation, exact full-body dispatch, file account ownership, removal of the denied alias, preservation of sibling aliases, and no reuse of the denied anchor.
- Grouped missing-tool-output settlement coverage verifies proxy-anchor retirement and unchanged client-anchor retention. The existing denial-ledger, durable cleanup, race, lifecycle, and owner-fence tests pass in the full bridge module.

### Checks

- `make lint`: passed, including architecture, cancellation, timing, settings, migration topology, Ruff, and formatting checks.
- `uv run --extra oracle ty check`: passed.
- `uv run --frozen pytest tests/unit/test_proxy_http_bridge.py tests/unit/test_http_continuation.py tests/unit/test_http_bridge_safe_continuity.py tests/unit/test_http_bridge_replay_rejection.py tests/unit/test_http_bridge_payload_dedupe.py -q --timeout=180 --timeout-method=thread --durations=10`: **1,151 passed**.
- `uv run --frozen pytest tests/unit/test_api_keys_service.py tests/unit/test_metrics.py -q --timeout=180 --durations=5`: **111 passed**.
- `npx --yes @fission-ai/openspec@1.11.0 validate fix-prompt-cache-tool-continuations --strict`: passed.
- `npx --yes @fission-ai/openspec@1.11.0 validate --specs`: **68 passed**.
- `git diff --check`: passed.

The full bridge run initially timed out inside the restricted sandbox during an existing SQLite retry-circuit lookup. The isolated test passed outside the sandbox in 1.16 seconds, and the full affected suite passed there in 44.49 seconds. The successful runs used temporary test databases and mocked upstream transports. Cache directories were scoped to `/tmp`; the pinned OpenSpec CLI was downloaded there and subsequently used offline. Tests emitted an existing Starlette/AnyIO deprecation warning.

### Coherence and limits

Recovery reuses the existing verified-body installation, account-neutral proof, file pin, pre-created retry, and durable denial fences. It adds no settings, migrations, or task lifecycles. Tool-bearing turns conservatively retain the full client request instead of attempting to deduplicate response-owned output from an input-only fingerprint.

No live provider, running server, or container was accessed. The supplied production logs do not include raw conversation bodies, so the exact input shape of each production rejection cannot be verified. The completion-to-submit fixture proves a concrete missing-output mechanism, while recovery and retirement address other upstream rejections of proxy-built continuations.
