# Tasks

- [x] Add the `priority` column to `api_key_accounts` with a fork-chain migration.
- [x] Persist caller order as rank through `replace_account_assignments`
      (INSERT..SELECT cannot preserve ordering, so carry it in a CASE).
- [x] Order the `ApiKey.account_assignments` relationship by `(priority, created_at)`.
- [x] Add `account_priority` to `select_account` and narrow the pool by best
      rank before the routing-policy partition.
- [x] Thread `account_priority` through the load balancer, the unbound selection
      path, and the shared budget-safe selector — excluding recovery probe
      reservation and opportunistic admission.
- [x] Build the rank map at the proxy request boundary from the ordered
      assignment list, independently of `account_assignment_scope_enabled`.
- [x] Make `account_assignment_scope_enabled` explicitly settable on create and
      update so ranking need not restrict.
- [x] Unit tests for the selection semantics (waterfall, failover, preserve
      interaction, unranked last resort, recovery carve-out, no-priority regression).
- [x] Integration tests for the rank round trip and reordering.
- [x] Dashboard: reorderable account list in the API key dialog + i18n
      (en/ko/zh-CN), plus an explicit "restrict to these accounts" toggle.
- [x] Make the edit dialog's change detection order-aware, so a pure reorder is
      submitted instead of being dropped by the set-based diff.
