# Processing-node context

The purpose is execution attribution, not host discovery or ingress inventory. Reuse `CODEX_LB_HTTP_RESPONSES_SESSION_BRIDGE_INSTANCE_ID`, a T1 topology value; no new setting is needed. Explicit `oci-a` and `home-b` are suitable labels. The hostname default remains internal to existing routing and is never published as provenance. Operators choosing labels are responsible for their meaning; syntax excludes addresses, domains and credential formats.

The central proxy request-log writer resolves the base Settings identity before scheduling detached persistence. It covers raw HTTP streaming/nonstreaming, compact, transcription, files, realtime, WebSocket finalization and bridge owner execution. Bridge forwarding returns before local finalization on success; the owner writes through the same central writer. A failed handoff can reach the origin wrapper before a receiver executes: those records remain unknown. A subsequent proven local recovery is local execution. Public headers cannot select provenance and no additional identity database read is needed.

For example, HTTP ingress on `oci-a` forwards to a bridge owner on `home-b`: the owner execution row returns `"processingNode": "home-b"`. An old row returns null even if read on `oci-a`. A request to an unreachable owner yields an origin error with null instead of guessing that the owner executed it.

Oracle has a separate immutable baseline. Add a descendant migration and evolve expected schema/transfer checks instead of rewriting the baseline. Offline dialect and migration tests establish representation compatibility; live Oracle validation remains external to this isolated work.

Rollout uses normal additive migrations. Older API consumers ignore the new nullable field; the new frontend accepts older backends. Downgrade discards only provenance. No filters or node index are needed for the compact display.


## Verified topology and writer inventory

- HTTP raw streaming/nonstreaming and retry attempts, compact, files, transcription, Codex controls/goals and realtime call `_write_request_log` in `proxy/_service/request_log.py`. Its existing tracked task writes through `RequestLogsRepository.add_log`; identity resolution requires no session or I/O.
- HTTP bridge requests run `_stream_http_bridge_or_retry`. Successful ingress owner-forwarding returns without a local execution row. The receiving signed `/internal/bridge/responses` route executes with its own Settings, and the shared WebSocket terminal/error/transport-end finalizers write the owner's row. Forwarding headers never carry public attribution.
- `_OwnerForwardRequestError` is server-owned forwarding provenance. On propagation without local recovery it produces an ingress failure row with null node and `bridge_stage=owner_forward`. Its status/error envelope and existing reservation cleanup remain authoritative. A pre-dispatch failure that permits bootstrap recovery returns to real local bridge submission; only the final local execution row is written.
- Downstream `/backend-api/codex/responses` and `/v1/responses` WebSocket routes call `proxy_responses_websocket` locally; they do not forward the client socket between instances. The HTTP bridge's remote owner holds the upstream WebSocket. Native WebSocket success, error, retry and final settlement reuse the same central writer.
- Model-source direct chat in `proxy/api.py` and owned Responses/chat dispatch in `proxy/source_dispatch.py` have independent log writers; both now supply the local safe identity. Automations, quota-planner warmup (success and error), and limit warmup supply it explicitly too. The detached scheduler adapter only forwards those already populated arguments. No other production `RequestLog` constructor bypasses the repository.
- Repository callers that omit provenance retain null. Listing, conversation mapping, aggregation and historical reads do not consult current Settings. There is no node lookup, node index, new configuration field, new navigation item or runtime host enumeration.

## Schema coordination

Default lineage: `20261101_000000_add_request_processing_node` follows `20261023_000000_renumber_api_key_account_priority`. Oracle: `20261101_000100_request_node` follows `20261024_000000_oracle_baseline`. The default upgrade adds only a nullable VARCHAR(64) column. Oracle adds VARCHAR2(64 BYTE) and verifies a surviving identical column before accepting an interrupted DDL restart. Its baseline JSON and baseline revision stay unchanged. `oracle_head_contract` evolves read-only drift/transfer expectations; installation continues through Alembic-owned DDL.

## Examples and operational limits

Explicit `home-b` on the executing owner yields `{"processingNode":"home-b"}` even if ingress was `oci-a`. A hostname default or unsafe ID yields null; known secret prefixes are also withheld. An explicitly chosen ordinary label can still contain sensitive meaning, so operators must use non-sensitive topology labels. No heuristic can prove an arbitrary operator string is not a secret.

The browser fixture fixes time at 2026-10-28 13:30 UTC and labels rows Synthetic fixture. No live dashboard or inference is involved. Offline Oracle checks and skipped live cases do not establish real Oracle acceptance. The repository's git-vs-disk topology test inherently differs while the new migration is uncommitted; the graph fitness checker is separately executed against the approved base without relaxing that test.

Oracle's native Alembic ledger uses VARCHAR2(32). The descendant ID deliberately stays under that bound; an offline test derives the actual Alembic Oracle version-table type and checks the head ID against it. No ledger widening or baseline edit is needed.
