# Usage Reporting

codex-lb records the token counts reported in the terminal Responses API event. It does not retokenize prompts or responses, and it does not estimate hidden reasoning usage.

For direct Codex traffic over HTTP or WebSocket, the reported buckets have these relationships:

- `input_tokens` includes the full input count; cached input is reported as a subset.
- `output_tokens` includes all generated output, including reasoning tokens.
- `reasoning_tokens` is the reported reasoning subset of `output_tokens`.
- Total tokens are `input_tokens + output_tokens`. Do not add cached input or reasoning tokens again.

## Dashboard

The **Request Logs** token cell shows total tokens, with reported cached-input and reasoning counts underneath. Open **Details** to see the exact reported reasoning count and its relationship to output tokens.

The **Reports** page shows the reported reasoning total for the selected date range and filters. Its coverage count states how many requests supplied a reasoning value. The daily breakdown and CSV export include the same reasoning field.

## Processing Node

Request Logs show **Node** beneath the account and **Processing node** in Details. This identifies the proxy instance that executed the request. If `oci-a` forwards a bridged request to `home-b`, the execution record identifies `home-b`. A forwarding failure with unconfirmed execution remains **Unknown**.

The label uses the existing `CODEX_LB_HTTP_RESPONSES_SESSION_BRIDGE_INSTANCE_ID` topology setting only when explicitly configured. Choose a non-sensitive label such as `oci-a` or `home-b`: 1–64 ASCII letters, digits, underscores or hyphens, starting with a letter. Addresses, domains, paths and recognized credential prefixes are withheld. The automatic hostname stays internal. Historical records and requests without a safe configured label show **Unknown**; reading them on another instance does not change their provenance.

*Spec: [proxy-runtime-observability](https://github.com/Soju06/codex-lb/tree/main/openspec/specs/proxy-runtime-observability)*

## Missing Usage

A reported zero remains `0`. A missing value remains unknown and appears as `—` in the daily report or is omitted from request details. codex-lb does not turn missing usage into zero.

Reasoning usage may be missing when the upstream terminal event does not include it, when a stream ends before that event arrives, or for older request-log rows. The dashboard does not backfill those rows. Custom OpenAI-compatible model sources do not currently feed reasoning details into this reporting path.

## Pricing and Missing Costs

codex-lb refreshes OpenAI text-token pricing hourly from models.dev. Compatible LiteLLM data supplies missing tier rates and additional models. Price lookups use the in-memory catalog; an upstream outage falls back to the last successful disk cache and bundled pricing snapshot. These amounts use API-equivalent token prices, not ChatGPT subscription credit multipliers.

When a model's price becomes available, retained subscription requests with missing costs are repaired automatically in small batches. Their dashboard, report, account, and API-key usage aggregates are corrected in the same transaction. Existing costs, including zero, and API-key limit counters are preserved. Requests whose raw logs have already been deleted by retention cannot be reconstructed.

The Codex client-version fallback is also retained across restarts. Bundled prices and the stable Codex version are maintained by a daily update workflow that opens a reviewable PR. Operators do not need an extra API key or configuration setting.

*Spec: [upstream-metadata](https://github.com/Soju06/codex-lb/tree/main/openspec/specs/upstream-metadata)*

---

*Spec: [frontend-architecture](https://github.com/Soju06/codex-lb/tree/main/openspec/specs/frontend-architecture)*
