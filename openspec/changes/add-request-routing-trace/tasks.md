# Tasks

- [x] `app/modules/proxy/routing_trace.py`: draft ContextVar, note helpers,
      trace builder with per-candidate eligibility, bounded store, log line.
- [x] Notes from the sticky and unbound pools, the sticky owner decision, and the
      budget-safe selector (serving rank, deciding pass).
- [x] `LoadBalancer.select_account(request_id=...)` captures, builds and records
      the trace; the proxy service passes the request id.
- [x] `GET /api/request-logs/{request_id}/routing` gated by `accounts:write`;
      route permission matrix updated.
- [x] Dashboard: "Routing decision" panel in the request details dialog (en / ko /
      zh-CN), MSW handler and coverage entry.
- [x] Tests: trace semantics against the real selector, store and redaction,
      API integration through the compact proxy route, panel rendering and
      permission gating.
- [x] Docs: "Why a request got its account" in `docs/routing.md`.
