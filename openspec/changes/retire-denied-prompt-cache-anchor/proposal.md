## Why

The opt-in prompt-cache continuation recovery path mutates away the provenance of a denied proxy-injected anchor before retiring it, and a successful retry returns before retirement entirely. If the fresh replay does not complete, a later full resend can therefore inject and dispatch the already-denied anchor again despite the existing denial fence contract.

## What Changes

- Retire and fence the exact denied proxy-injected prompt-cache anchor before installing or sending the fresh full-resend replay body.
- Preserve a newer sibling completion and all unrelated response aliases, account ownership, and file ownership while retiring only the denied anchor.
- Add a hermetic bridge-level regression covering both fresh-replay send outcomes, default-off controls, full replay proof, next-submit non-reuse, preservation, and the retirement/dispatch race.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `responses-api-compat`: make the existing first-denial retirement and dispatch-fencing contract explicit for prompt-cache full-resend fallback, including retirement before provenance mutation or retry early return.

## Impact

- **Proxy:** HTTP bridge handling of `previous_response_not_found` for proxy-injected prompt-cache continuation anchors.
- **Tests:** focused unit regression using synthetic state and mocked transport/persistence boundaries only.
- **Compatibility:** no API, schema, setting, migration, dashboard, or default behavior change; client-supplied anchors remain untouched.
