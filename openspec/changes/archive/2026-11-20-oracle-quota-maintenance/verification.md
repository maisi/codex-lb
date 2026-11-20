# Verification

## Repository checks

- 27 targeted backend tests passed, including quota boundaries, an interrupted run, partial failure and retry delays, SQLite and PostgreSQL gating, dashboard access control and lifecycle checks.
- The separate Oracle integration test passed on a locally provisioned Oracle Free database with the application schema installed by the normal migrations. Two physical connections verified that the maintenance lock survives an online index rebuild and status commits, and becomes available when the owner releases its session.
- 42 frontend tests passed across the storage notice, dashboard, localization and mock API coverage. The frontend production build, TypeScript, changed frontend ESLint checks, Python Ruff and changed application type checks passed.
- Three browser checks on the production build covered a healthy dashboard, a manual warning at 2.5 GiB and running automatic maintenance at 1.5 GiB. Captures use synthetic dashboard data.

## Database exercise

A real background worker polled a disposable Oracle Free schema with a 2,100 MiB quota. After a synthetic event burst and deletion, free quota was 1,387,397,120 bytes. The worker started without a dashboard request and brought free quota to 2,200,895,488 bytes. The retained event still had its original ID and text, all indexes were valid, and the new quota correctly remained in the manual warning range. A separate request-table exercise reclaimed approximately 538 MiB.

[Healthy dashboard](evidence/before.jpg) · [Manual warning](evidence/manual.jpg) · [Automatic maintenance](evidence/automatic.jpg)
