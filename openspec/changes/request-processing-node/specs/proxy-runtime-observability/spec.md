# Spec Delta

## ADDED Requirements

### Requirement: Request records identify their processing node
Request records MUST persist nullable `processing_node` provenance from the execution runtime. Request API entries MUST expose optional nullable `processingNode` defaulting to null. Reads MUST use persisted provenance and MUST NOT infer it from ingress, account, transport or current runtime.

#### Scenario: Local execution is recorded through settlement
- **WHEN** a locally executed HTTP, SSE or WebSocket request writes a success, retry, cancellation or error record
- **THEN** its processing node is the safe explicitly configured execution identity, or null when unavailable
- **AND** usage, account ownership and settlement behavior are preserved

#### Scenario: Historical or omitted identity stays unknown
- **WHEN** a historical request row or a caller omitting the optional API field is serialized
- **THEN** processingNode is null without consulting the reading runtime

### Requirement: Processing identity exposes only a safe explicit label
Processing identity MUST reuse only the explicitly configured bridge instance ID. Unset IDs MUST yield null even when routing defaults to hostname. Labels MUST contain 1–64 ASCII letters, digits, underscores or hyphens and start with a letter. IDs containing addresses, domains, paths, whitespace or recognized credential prefixes MUST yield null without breaking operation. Runtime host inventory MUST NOT supply public provenance.

#### Scenario: Explicit operator labels are safe to display
- **WHEN** the instance ID is explicitly set to `oci-a` or `home-b`
- **THEN** request provenance stores that label

#### Scenario: Defaults and unsafe labels do not leak inventory
- **WHEN** the ID is unset, empty, an IP, a domain, a URL, a path or a credential-bearing value
- **THEN** request provenance is null


#### Scenario: Credential-shaped instance IDs remain private
- **WHEN** an explicit ID starts with `sk-`, `gh[opusr]_`, `github_pat_`, `xox[baprs]-`, `AKIA` or `ASIA` (case-insensitive)
- **THEN** request provenance is null
