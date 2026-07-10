# Outbound HTTP Clients Context

## Purpose

This capability defines the outbound identity and transport behavior used for OAuth and ChatGPT Codex upstream calls. Normative requirements are maintained in [spec.md](spec.md).

## Codex Responses Identity

ChatGPT Codex model rollout can depend on the combination of `originator`, `version`, and `User-Agent`. For non-native Responses clients, codex-lb replaces those identity headers with one internally consistent Codex CLI fingerprint instead of forwarding third-party or SDK values. The version is taken from the existing cached Codex-version source, so request handling does not perform network I/O.

Native Codex traffic is not rewritten. This preserves first-party client identity while preventing generic OpenAI SDK clients from selecting an unrelated rollout cohort.

For example, a non-native request that provides `originator: pi` and `version: 0.80.6` is forwarded with:

```text
originator: codex_cli_rs
version: <cached Codex version>
User-Agent: codex_cli_rs/<cached Codex version> (...)
```

## Failure Modes

- An account can list a model but still receive an upstream model error if its entitlement is unavailable; fingerprint normalization does not bypass account eligibility.
- If the version cache has not yet been warmed, the configured Codex client-version default is used.
- Upstream identity requirements can change; update the shared fingerprint normalizer and its HTTP and websocket regression coverage together.

## Related Contracts

- [Responses API compatibility](../responses-api-compat/spec.md) defines the client-facing Responses behavior.
- [Model catalog compatibility](../model-catalog-compat/spec.md) defines model availability and bootstrap behavior.
