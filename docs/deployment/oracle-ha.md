# Oracle two-instance failover pilot

Two single-worker codex-lb instances can share an Oracle application schema behind a readiness-aware load balancer. If one process dies, its active stream can break; new requests and eligible client retries go to the survivor. Transparent continuation of that stream is a later milestone. The acceptance test uses real application processes and Oracle connections with a controlled upstream; it does not establish physical-host, network-partition or live upstream availability.

Owning specifications: [Oracle database](https://github.com/maisi/codex-lb/tree/main/openspec/specs/oracle-database) and [replica operations](https://github.com/maisi/codex-lb/tree/main/openspec/specs/replica-operations). See their context documents for the acceptance boundary and the [stream-continuation assessment](https://github.com/maisi/codex-lb/blob/main/openspec/specs/replica-operations/oracle-ha.md#transparent-stream-continuation).

## Provision the shared dependencies

Install with `uv sync --frozen --extra oracle` on both hosts. Follow the [Oracle database setup](../database.md#oracle-autonomous-database) for a dedicated application schema, migration grants, the protected `CODEX_LB_DATABASE_URL` and wallet mounts. Use the same schema and selected TP service on both hosts; keep certificate verification enabled.

Mount **identical encryption key bytes** at `/run/secrets/codex-lb/encryption.key` on both hosts, readable only by the service user. Reuse the original key when adding a peer to an existing installation. Independently generated keys cannot decrypt shared account credentials or authenticate peer forwarding; leave fingerprint enforcement enabled. Each host keeps its own persistent data directory and local conversation archives. The database and key need separate backups.

Provide a unique bridge instance ID and a directly reachable peer URL on each host. That URL identifies one process; it must not point at the load-balancer VIP or a shared service name. The load balancer and both peers must reach these addresses. Keep leader election enabled and use one application worker per instance; the `codex-lb` launcher already starts one worker.

For example, configure the following existing settings in each service's protected environment file, alongside its database URL and other deployment secrets:

| Setting | Host A | Host B |
| --- | --- | --- |
| `CODEX_LB_DATA_DIR` | `/var/lib/codex-lb/ha-a` | `/var/lib/codex-lb/ha-b` |
| `CODEX_LB_ENCRYPTION_KEY_FILE` | `/run/secrets/codex-lb/encryption.key` | `/run/secrets/codex-lb/encryption.key` |
| `CODEX_LB_HTTP_RESPONSES_SESSION_BRIDGE_INSTANCE_ID` | `ha-a` | `ha-b` |
| `CODEX_LB_HTTP_RESPONSES_SESSION_BRIDGE_ADVERTISE_BASE_URL` | `http://10.20.0.11:2455` | `http://10.20.0.12:2455` |

These HTTP addresses assume a trusted private network. Use HTTPS or a protected network tunnel when peer traffic requires transport encryption. Apply the normal dashboard authentication and trusted-proxy configuration before exposing the front door.

## Start and route traffic

With the protected environment loaded, initialize/check the schema, then start each host:

```sh
uv run --extra oracle codex-lb-db oracle-check
uv run --extra oracle codex-lb-db upgrade head
uv run --extra oracle codex-lb-db check
uv run --extra oracle codex-lb --host 0.0.0.0 --port 2455
```

Start A first and verify `/health/ready`, then start B and verify both direct readiness endpoints. Startup migration locking coordinates the shared schema; upgrading explicitly before traffic makes installation failures visible before enabling the backends.

Adapt the repository's [HAProxy example](https://github.com/maisi/codex-lb/blob/main/deploy/oracle-ha/haproxy.cfg) to the two private addresses. Its listener is `127.0.0.1:2455` on a separate gateway host, behind an operator-provided TLS ingress. Validate and start it with your service manager:

```sh
haproxy -c -f deploy/oracle-ha/haproxy.cfg
haproxy -db -f deploy/oracle-ha/haproxy.cfg
```

Readiness checks use `/health/ready`, including database readiness and drain state. `/health/live` alone is insufficient for routing. The example checks every second, removes a backend after two failures and restores it after two successes; these are detection settings, not an end-to-end failover guarantee. Connection timeouts and health-check execution can add delay.

The affinity cookie improves continuity when clients retain it. Database-backed ownership and direct peer forwarding remain necessary because clients may omit cookies. `retries 0` prevents HAProxy from replaying an uncertain POST. Keep that behavior, allow SSE/WebSocket streaming through the TLS ingress, and deny public access to `/internal/*`. Scrape metrics directly from each instance rather than through the VIP.

### OCI Load Balancer

An OCI Load Balancer can take HAProxy's place. Configure the equivalent behavior explicitly:

- **Listener:** use an HTTP listener (or HTTPS terminating TLS at the load balancer), not TCP, so health checks, cookie persistence and forwarded headers apply. The HTTP listener's idle timeout defaults to 60 seconds and closes a quiet SSE or WebSocket stream; raise it above the longest silent gap you expect, up to the two hours used in the HAProxy example.
- **Backend set health check:** HTTP `GET /health/ready`, expected status `200`. The default 10-second interval with three retries can take about 30 seconds to remove a dead or draining instance, which matches the default drain budget. Shorten it (for example a 1–2 second interval with two retries) or raise `CODEX_LB_SHUTDOWN_DRAIN_TIMEOUT_SECONDS`.
- **Session persistence:** enable load-balancer cookie persistence on the backend set. It replaces the HAProxy affinity cookie; database ownership and peer forwarding still cover clients that drop it.
- **Client addresses:** the HTTP listener adds `X-Forwarded-For`. To use it for firewall and dashboard decisions, set `CODEX_LB_FIREWALL_TRUST_PROXY_HEADERS=true` and `CODEX_LB_FIREWALL_TRUSTED_PROXY_CIDRS` to the load balancer subnet only. Start instances with the `codex-lb` launcher, which keeps Uvicorn's own proxy-header rewriting off; do not run Uvicorn with `--proxy-headers` and `FORWARDED_ALLOW_IPS=*`.
- **`/internal/*`:** load balancer rule sets cannot deny by path. Drain/stop/status accept only loopback callers and bridge routes require a signature derived from the shared key, so they are not exposed through the load balancer. If you add an edge block (for example an OCI WAF rule), match the URL-decoded path.
- **Network:** security lists or network security groups must allow the load balancer subnet to reach both instances on `2455` and the instances to reach each other on `2455`. Advertise each instance's private VCN address, never the load balancer address.
- **Retries:** confirm the load balancer does not replay a POST that reached a backend; the client remains responsible for retries.
- **Replacement:** add the new backend and wait until the load balancer reports it healthy, then set `drain` on the old backend (or start the instance's `/internal/drain/start` locally, which fails its readiness check), wait for `in_flight` to reach zero, and remove it.

## Recovery and replacement

| Event | Expected boundary |
| --- | --- |
| Application process dies | The load balancer removes it. An active response can end abruptly; the client decides whether to retry. A retry can execute upstream again, so this is not exactly-once upstream execution. |
| Scheduler leader dies | Singleton work transfers after the existing lease expires. The production lease TTL defaults to **60 seconds**, plus acquisition/scheduling delay. Ordinary requests do not wait for scheduler leadership. |
| Session owner dies | Continuity recovery respects owner/account fences. The bridge ring and durable lease use a **30-second** stale/lease interval; expiry alone does not make every uncertain operation replayable. Honor retry/error responses rather than dropping session identifiers or changing accounts. |
| A request loses settlement ownership | Its reservation remains conservative. Stale cleanup becomes eligible after **six hours** without heartbeat, or a **24-hour** hard age ceiling, and runs on the leader's hourly reset pass. This can temporarily consume API-key quota. |
| Shared Oracle or gateway fails | Both instances can become unavailable. This pilot provides application-process failover; database and gateway redundancy require separate infrastructure. |

For a planned replacement, start the replacement with a new instance ID and its own direct URL. Add it to `backend codex_instances` before removing the old backend; for example:

```haproxy
    server ha-c 10.20.0.13:2455 cookie ha-c check inter 1s fall 2 rise 2
```

Validate the edited configuration with `haproxy -c`, then use your service manager's **graceful reload** to preserve existing streams. Verify the replacement's direct readiness and that the gateway has marked its backend healthy. Drain the old process only after that. On the old host, using its loopback listener:

```sh
curl --fail -X POST http://127.0.0.1:2455/internal/drain/start
curl --fail http://127.0.0.1:2455/internal/drain/status
```

Readiness becomes 503. Wait until the gateway has removed that backend and `in_flight` reaches zero, then stop it through the service manager. Remove its old HAProxy server entry, validate and gracefully reload again. Drain is bounded by `CODEX_LB_SHUTDOWN_DRAIN_TIMEOUT_SECONDS` (default **30 seconds**); work exceeding that budget can be interrupted. SIGTERM also starts the admission/drain barrier. Allow sufficient service-manager termination grace for drain and cleanup. Before process shutdown commits, `/internal/drain/stop` can cancel an operator drain; otherwise restart the process to restore service.

Oracle defaults are four connections and zero overflow in each of two pools: **16 application sessions** for A+B, **24** with one replacement. Leave the remaining six of the 30-session budget for migration, administration and other users; the migration peak needs two connections. Explicit pool overrides change this calculation. Check it before rollout:

```sh
uv run --extra oracle codex-lb-db oracle-check --budget-only \
  --pool-size 4 --max-overflow 0 --replicas 2 --extra-replicas 1
```

This is a connection budget, not a throughput guarantee. The Free database remains a shared resource and availability dependency.

## Reproduce acceptance

Install native HAProxy, make `ha-a.localhost`, `ha-b.localhost` and `ha-c.localhost` resolve to `127.0.0.1` (for example through `/etc/hosts`; the instances advertise these replica-specific names to each other), and provide a separate, empty schema in the protected `CODEX_LB_TEST_ORACLE_HA_URL` test environment variable. This target must be disposable: the test installs application objects and removes its own objects afterward. It refuses an existing table, view or sequence before application initialization. Then run:

```sh
uv run --extra oracle pytest -q -s tests/integration/test_oracle_ha.py
```

The scenario covers independent processes, settings invalidation, singleton ownership, a competing token refresh, crash/client retry, accounting, restart and planned drain with replacement overlap. It prints `oracle_ha_acceptance` timing/budget evidence. Test-only shorter lease/drain intervals are not production defaults. Use the Oracle CI workflow for the complete native Oracle regression suite.
