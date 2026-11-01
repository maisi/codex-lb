# Spec Delta

## ADDED Requirements

### Requirement: Bridge processing provenance follows execution ownership
Bridge forwarding MUST attribute execution records to the receiving execution runtime, never the ingress or an inbound claimed identity. Public headers and forwarded origin metadata MUST NOT set processing provenance. A forwarding-only failure with unconfirmed execution MUST record null provenance. Local recovery MUST record the recovering runtime when it executes.

#### Scenario: An owner receives a forwarded request
- **WHEN** authenticated HTTP bridge forwarding carries work over an owner-held upstream WebSocket from `oci-a` to `home-b`
- **THEN** the execution record identifies `home-b`, including upstream errors and final settlement
- **AND** the ingress creates no duplicate successful execution record

#### Scenario: Owner forwarding fails before execution is confirmed
- **WHEN** an owner is unreachable or rejects a forwarded request before accepting execution
- **THEN** any ingress failure record has null processingNode
- **AND** reservation release and fail-closed continuity behavior are preserved

#### Scenario: Spoofed node headers are ignored
- **WHEN** a public client supplies node or bridge-origin headers
- **THEN** locally executed work records only the local safe identity
