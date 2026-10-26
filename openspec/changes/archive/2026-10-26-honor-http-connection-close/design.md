## Context

The OCI LB's .39 primary and .131 secondary addresses are confirmed on the same
VNIC. TCP connections from .131 reach the app and receive 200. OCI still reports
CONNECT_FAILED. Its request uses `Connection: Close`; the current protocol fails
to close it and subsequently stops answering on that socket.

## Goals / Non-Goals

Honor HTTP connection-close semantics without health-specific response handling
or changes to readiness meaning, keep-alive defaults, routing or SQLite.

## Decisions

Use httptools' existing `should_keep_alive()` decision at completed headers. When
the parser disallows persistence, append a canonical lowercase close field if
absent, before Uvicorn creates its response cycle. Preserve original fields and
the existing upgrade replay; replay retains non-upgrade Connection tokens.
The h11 fallback already understands close tokens and needs no implementation
change. Use both adapters in actual TCP readiness tests.

## Risks / Trade-offs

- Protocol changes can affect keep-alive and upgrades: run existing upgrade,
  disconnect-stamp and timer regressions alongside new socket tests.
- A protocol defect does not prove incident causality: a reversible production
  trial must verify actual probe EOF and public recovery independently.
- A runtime patch can disappear on image replacement: retain original source
  and record exactly what was applied; permanent rollout requires the source fix.
