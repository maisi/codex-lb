## ADDED Requirements

### Requirement: Native Codex capacity rejections use bounded recovery

The proxy MUST recognize `Codex is at capacity, please try again later` as temporary capacity evidence. An HTTP bridge MUST apply its existing bounded capacity wait and replay rules before surfacing an eligible output-free rejection, preserving the original deadline, stronger quota classifications, and public stream framing.

#### Scenario: Native capacity 429 recovers
- **WHEN** upstream rejects a replayable bridge request with `turn_rate_limit_exceeded` and the native capacity message before response output
- **THEN** the bridge waits before its bounded retry
- **AND** a successful retry completes without exposing an intermediate 429 or duplicate response lifecycle

#### Scenario: Output and ambiguous dispatch remain protected
- **WHEN** response output was delivered or dispatch failed without definitive rejection evidence
- **THEN** the proxy preserves the existing partial-output or ambiguous-outcome behavior

### Requirement: Temporary continuity owner backoff is waited out once

An HTTP bridge MUST allow an active continuity owner up to 30 seconds to recover from known local transient backoff before attempting relocation or surfacing owner unavailability. The wait MUST stay within the original request deadline, release account capacity, honor cancellation, and never bypass selection policy.

#### Scenario: Owner recovers during the bounded wait
- **WHEN** selection rejects the required owner while it is active and has a known transient backoff deadline
- **THEN** the bridge waits and reselects the same owner without altering the request or conversation anchor
- **AND** a successful turn does not produce an intermediate 502

#### Scenario: Persistent or excluded owner is not waited out
- **WHEN** the owner is paused, quota-blocked, missing, outside policy, or excluded by this request
- **THEN** this transient recovery wait is not applied

#### Scenario: Backoff does not extend the request budget
- **WHEN** the owner remains backed off beyond the recovery window or the request is cancelled
- **THEN** the bridge stops waiting without dispatching after the deadline or retaining a task or lease

### Requirement: Definitive bridge owner loss can use a complete stored transcript

After selection-time owner unavailability, an HTTP bridge MUST attempt a bounded reconstruction of the anchored conversation from complete, settled durable turns when client full-resend proof is unavailable. Relocation MUST require scoped durable ownership, a complete parent chain, account-neutral content and settled tools. It MUST preserve current client input and exclude the failed owner through normal selection.

#### Scenario: Delta continuation relocates exactly once
- **WHEN** an unavailable owner has a complete scoped transcript and the new turn is portable
- **THEN** the bridge sends the reconstructed conversation without the old anchor on an eligible replacement account
- **AND** the current turn is dispatched exactly once and subsequent turns retain replacement ownership

#### Scenario: Root and replacement turns are recorded
- **WHEN** an unanchored root or reconstructed replacement request completes with fully represented response output
- **THEN** the bridge records the exact request and settled response through the existing bounded operation spool
- **AND** independent identical unanchored requests receive distinct operation identities
- **AND** optional recording failure does not fail the completed response or permit incomplete reconstruction

#### Scenario: Recording differences do not duplicate history
- **WHEN** the client resends a suffix of the stored conversation with different recording IDs or bookkeeping fields
- **THEN** only the matching stored tail is replaced by the client's items
- **AND** a coincidental match elsewhere does not delete or reorder current input

#### Scenario: Unsafe or incomplete history fails closed
- **WHEN** the chain is missing, cyclic, incomplete, over its turn, byte or item bounds, or contains account-scoped state or unsettled tools
- **THEN** the bridge preserves its existing owner-unavailable failure without dispatching to another account

#### Scenario: Binding and dispatch evidence constrain relocation
- **WHEN** routing is single-account, files bind the turn, durable scope is absent, output was delivered, or upstream acceptance is ambiguous
- **THEN** stored-transcript relocation is refused

## MODIFIED Requirements

### Requirement: Verified full resend can recover from selection-time owner loss

An HTTP bridge request MAY move from an unavailable continuity owner to another account only after a typed pre-visible `continuity_owner_unavailable` account-selection result, which the HTTP bridge maps to `previous_response_owner_unavailable`, and either positive client full-resend proof or a complete scoped stored transcript under the stored-transcript recovery requirement. A missing durable owner is not a selector result and MUST fail closed without replay. For client full-resend proof, the durable row MUST provide a positive input-item count and full fingerprint, and the corresponding raw prefix of the incoming list-shaped input MUST match both before any projection occurs.

In the client full-resend lane, after the raw prefix proof, the service MUST construct a deterministic plaintext projection by omitting `reasoning`, `web_search_call`, `tool_search_call`, and `tool_search_output` items and removing upstream `id` fields from every retained input item. Retained `internal_chat_message_metadata_passthrough` MUST contain only a nonblank string `turn_id` when present. The projected suffix after the projected prefix MUST contain a completed assistant `output_text` or `refusal` boundary with nonblank content followed by nonblank fresh text or valid fresh file/image input. The suffix MAY contain multiple intervening turns only when every non-final user-input sequence is followed by another completed assistant boundary and the final sequence ends in fresh input. Direct intrinsic calls MAY precede an assistant boundary only when terminal completed or failed outputs settle every represented call in order. A call at the end of the verified raw prefix MAY be settled by its matching output at the start of the suffix. A direct-call/output sequence alone MUST NOT prove completeness because the persisted metadata does not identify omitted parallel calls. Without complete stored-transcript proof, a matching prefix followed only by new user input, empty content, tool-call-only output, in-progress or partial retained output, duplicate, unmatched, or unresolved calls, or misordered call output MUST fail closed.

The service MUST validate the complete projected request after removing `previous_response_id`; it MUST reject nonblank conversation or prompt handles, remaining encrypted content, compaction, opaque account-scoped file/container/vector handles, nonportable file schemes, hosted, MCP, program-mediated, or unknown call or tool-choice state, unknown top-level fields, unknown or malformed top-level reasoning configuration, malformed message/content shapes, and tool outputs without exactly one matching intrinsic call. Assistant messages MUST contain only supported output parts, while user, system, and developer messages MUST contain only supported input parts. Inline data images and HTTP(S) file/image content MAY remain eligible. Eligible declared tools, tool choices, and retained direct calls MUST be shape-validated, account-neutral, and self-contained. Web-search filters, context size, and approximate location MUST use only the recognized nested fields and value types. An apply-patch call MUST use exactly one representation: a recognized structured `operation` with its exact discriminated fields, a nonblank legacy `patch`, or a nonblank legacy `input`.

For an eligible replay, the service MUST remove `previous_response_id`, strip every downstream session/turn alias, clear hard affinity, exclude the unavailable owner, prevent initial bridge-owner forwarding, and submit the complete projected request through a fresh server-namespaced recovery lane. It MUST NOT replay after downstream-visible output. Selection policy conflicts, authentication/connection failures after selection, history incomplete in both recovery lanes, or any unsafe request state MUST remain fail-closed.

#### Scenario: Client-supplied full resend moves from A to B

- **GIVEN** account A owns a completed previous response and its durable row stores the completed input count and fingerprint
- **AND** a follow-up supplies that previous response plus an account-neutral full resend whose retained prefix matches both values
- **WHEN** required-owner selection returns typed `continuity_owner_unavailable` before output
- **THEN** the bridge removes the previous-response anchor and all stale affinity headers
- **AND** excludes account A and submits the complete fresh request once on account B
- **AND** the next turn for the recovered task remains on account B

#### Scenario: Proxy-injected anchor protects an equivalent full resend

- **GIVEN** a hard durable alias resolves a completed response and the incoming full resend matches its retained count and fingerprint
- **AND** the proxy injects that response as the reattach anchor
- **WHEN** required-owner selection returns typed `continuity_owner_unavailable` before output
- **THEN** the same fresh-replay rules apply after the injected anchor is removed

#### Scenario: Verified resend contains owner-bound reasoning

- **GIVEN** a verified full resend contains encrypted reasoning, server-assigned item IDs, and completed web or tool-search bookkeeping
- **AND** its retained assistant and direct-tool content is otherwise complete and portable
- **WHEN** required-owner selection returns typed `continuity_owner_unavailable` before output
- **THEN** the bridge omits the reasoning and search bookkeeping and strips upstream item identities
- **AND** no encrypted content or upstream item identity is sent to account B
- **AND** the validated plaintext projection is submitted once on account B

#### Scenario: Retained request contains account-scoped state

- **GIVEN** a full resend contains a conversation or prompt handle, compaction, encrypted content outside an omitted reasoning item, an opaque account-scoped file/container/vector handle, a nonportable file scheme, hosted or MCP call or tool-choice state, an unknown call type, or an unmatched tool output
- **WHEN** its required owner is unavailable
- **THEN** the request fails with `previous_response_owner_unavailable`
- **AND** none of that state is sent to another account

#### Scenario: Request shape is not completely understood

- **GIVEN** a purported full resend contains an unknown top-level field or malformed/unknown message content
- **WHEN** its required owner is unavailable
- **THEN** replay eligibility fails closed
- **AND** the service does not infer portability from the retained fingerprint alone

#### Scenario: Matching input prefix omits the prior response output

- **GIVEN** the incoming input prefix matches the durable count and fingerprint
- **AND** the suffix contains only a new user message, a direct-call/output sequence without a later completed assistant boundary, partial retained output, or unresolved direct calls
- **AND** complete portable stored-transcript proof is unavailable
- **WHEN** the required owner is unavailable
- **THEN** replay eligibility fails closed with `previous_response_owner_unavailable`
- **AND** the proxy does not drop the previous-response anchor or send the incomplete transcript to another account

#### Scenario: Owner was selected before a later failure

- **GIVEN** the required owner was selected successfully
- **WHEN** refresh, authentication, WebSocket connection, transport, or timeout fails before output
- **THEN** the request keeps that ordinary failure classification
- **AND** the service does not activate cross-account full-resend recovery

#### Scenario: Durable continuity row has no account owner

- **GIVEN** a durable continuity row proves retained input but has no account owner
- **WHEN** the request is evaluated before account selection
- **THEN** the bridge returns `previous_response_owner_unavailable`
- **AND** it does not treat the missing owner as a typed selector miss or replay on another account

#### Scenario: Failure occurs after visible output

- **WHEN** any part of a response has become downstream-visible
- **THEN** the service does not replay the request on another account
- **AND** it terminates through the existing partial-output failure contract
