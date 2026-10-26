# Oracle process-failover context

The normative topology contract is in [spec.md](spec.md), with Oracle-specific requirements in [oracle-database/spec.md](../oracle-database/spec.md). The published [operator guide](../../../docs/deployment/oracle-ha.md) and [HAProxy configuration](../../../deploy/oracle-ha/haproxy.cfg) give a concrete two-host example.

## Purpose and acceptance boundary

This pilot joins two independently identified, single-worker application processes to one Oracle schema, encryption key and readiness-aware gateway. A third process exercises replacement overlap. It builds on existing database ownership primitives rather than adding another coordinator or changing lease defaults.

Acceptance uses real TCP application processes, HAProxy, native Oracle pools and real request reservation/settlement. The upstream and OAuth endpoints are controlled wire mocks so process death can be reproduced without real account credentials. Two processes on one test host establish process-loss behavior; they do not establish independent host, network-partition or upstream-service availability. The same harness can run against an isolated OCI TP schema.

The example leaves POST replay disabled. A process can die after upstream acceptance but before durable completion; making the load balancer retry that request could generate twice. Completed local accounting follows the existing settlement path, while an orphan keeps its conservative reservation until existing cleanup criteria apply. A client retry and exactly-once upstream execution are distinct promises.

## Operational decisions and failure modes

- One shared key protects stored credentials, dashboard sessions and authenticated bridge forwarding. The startup fingerprint guard catches disagreement. Do not disable it to admit an incorrectly provisioned peer.
- Unique process endpoints allow a request arriving at B to reach an A-owned session. A shared VIP cannot identify that owner. A restarted process gets a new process epoch even when it reuses its stable instance ID.
- Scheduler lease TTL defaults to 60 seconds. The bridge ring stale threshold and durable session lease are 30 seconds. Their expiry controls ownership, not unconditional replay eligibility. Fail-closed continuity responses remain necessary when an upstream outcome is unknown.
- Reservation cleanup is eligible after six hours without heartbeat or a 24-hour hard lifetime and runs on an hourly leader pass. Artificially aging only the test's orphan row verifies that policy without changing production timing.
- Four slots in each of two pools yield eight application connections per process, sixteen with two processes and twenty-four with a replacement. Administrative sessions and the two-connection migration peak need separate headroom. The tests hold actual pool slots concurrently rather than relying on arithmetic alone.
- The Free database, gateway, wallet/key provisioning and network remain common dependencies. This sprint does not introduce database failover, a redundant gateway or transparent active-stream takeover.

For example, A can accept a streamed request and then be killed after the first event. HAProxy removes A; B handles a fresh request or eligible client retry. The interrupted request's reservation is not immediately refunded just because A disappeared. A later restart must respect the successor's owner epoch and the original account pin. During planned drain, readiness closes new admission while accepted work finishes within the bounded shutdown deadline.

Any readiness-aware HTTP load balancer can serve as the gateway; the HAProxy file is the tested example. On an OCI Load Balancer the equivalents are an HTTP listener whose idle timeout exceeds the longest silent stream gap (its 60-second default cuts quiet streams), an HTTP `/health/ready` check whose interval and retries fit inside the drain budget (the default 10 s × 3 roughly consumes the 30-second default), load-balancer cookie persistence, and trusted-proxy CIDRs limited to the load balancer subnet. Internal routes stay protected without a gateway path block: drain/stop/status require a loopback caller, the launcher keeps Uvicorn proxy-header rewriting off so a forwarded client is never seen as loopback, and bridge routes require a signature from the shared key. A gateway deny remains defense in depth and must match the decoded path.

## Transparent stream continuation

There are two separate lifetimes to preserve: the upstream generation and the client connection. The shared database already persists operation fingerprints and ordered event spools, but it does not transfer either live socket from a dead process. Existing completed/incomplete-operation replay requires a complete spool; an uncertain previously dispatched operation fails closed rather than being blindly submitted again.

Current-code evidence:

- [`request_submit.py`](../../../app/modules/proxy/_service/http_bridge/request_submit.py) checks terminal operation state and `event_spool_complete` before replay, and returns `upstream_operation_status_unknown` when a prior dispatch has no safe replay/status proof.
- [`durable_bridge_repository.py`](../../../app/modules/proxy/durable_bridge_repository.py), `get_operation_events`, reads events in sequence order and validates stored byte counts. This is a foundation for replaying durable output, not proof that an unfinished generation can be recovered after process death.

Official OpenAI documentation describes a possible upstream mechanism for the **public Responses API**: create with `background=true` and `stream=true`, retain the response ID and event `sequence_number`, then resume with `GET /v1/responses/{id}?stream=true&starting_after=N`. See [Streaming a background response](https://developers.openai.com/api/docs/guides/background#streaming-a-background-response). That guide does not establish support on the ChatGPT `/backend-api/codex/responses` endpoint used by this project. No live upstream capability probe is part of this sprint.

The next bounded experiment should establish:

1. Whether the actual configured endpoint/account supports background execution, response lookup and cursor-based resume after the original connection closes, including its retention and authentication limits. The public API's behavior cannot be assumed for ChatGPT backend traffic.
2. Whether a stable gateway can retain the client stream while switching only its upstream connection, with durable response ID/cursor checkpoints, event deduplication and explicit delivery/commit ordering. If the client-facing gateway itself dies, retaining an ordinary TCP connection requires another design or a client reconnect protocol.
3. Whether owner fencing and settlement remain correct when a worker dies before checkpoint commit, after output persistence, during downstream delivery or during settlement. Test byte gaps/duplicates and tool-call boundaries, not only a final concatenated string.

If upstream resume is unavailable, an execution worker that survives either serving application's loss could preserve a generation, but it becomes a separate availability boundary and does not solve loss of that execution worker. Shared event storage alone cannot reconstruct output never received. A later implementation therefore needs capability evidence before promising seamless recovery or estimating it as a small extension of this pilot.
