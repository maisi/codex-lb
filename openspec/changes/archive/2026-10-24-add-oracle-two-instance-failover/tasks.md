## 1. Contract and isolation

- [x] 1.1 Create proposal, design, delta specifications and this implementation checklist; verify OpenSpec recognizes all artifacts.
- [x] 1.2 Add a dedicated empty-schema HA test target and owned-process fixture; verify pre-existing tables are preserved and cleanup works after partial startup.

## 2. Real-process failover acceptance

- [x] 2.1 Start two independently identified application processes and HAProxy using the same Oracle schema and key; verify direct and load-balanced readiness plus cross-process settings/cache visibility.
- [x] 2.2 Verify production leader protection and refresh-claim exclusion across independent application processes; verify only one process performs singleton work and one token exchange wins concurrent refresh.
- [x] 2.3 Kill the serving process during a controlled request; verify a client retry succeeds on its peer, completed usage settles once and orphaned reservations follow the existing bounded conservative policy.
- [x] 2.4 Restart the former owner and exercise continuity ownership fences; verify stale owners cannot overwrite a successor or cross account pins.
- [x] 2.5 Exercise planned drain and replacement overlap; verify readiness eviction, successful accepted-work completion and the sixteen/twenty-four-session application pool budget.
- [x] 2.6 Fix any product defect exposed by those acceptance paths and verify focused regressions on existing SQLite/PostgreSQL behavior.

## 3. Delivery and evidence

- [x] 3.1 Add a reproducible HAProxy/operator example and OpenSpec-linked guide; verify configuration syntax and document shared secrets, lease/retry timing, reservation expiry and shared dependency limits.
- [x] 3.2 Record transparent stream continuation feasibility with concrete current-code/upstream evidence and a proposed next experiment, without claiming takeover support.
- [x] 3.3 Run the complete real-process acceptance on local Oracle and the supplied OCI TP database; verify exact results, measured failover times, clean schema and bounded process cleanup.
- [x] 3.4 Add HA acceptance to Oracle CI; verify the final published check, relevant regressions, lint/type gates and strict OpenSpec validation.
- [x] 3.5 Publish a focused stacked HA PR, sync verified contracts/context, verify and archive this change; inspect the actual PR head and report remaining support boundaries.
