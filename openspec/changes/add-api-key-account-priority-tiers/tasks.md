# Tasks

- [x] Accept `assigned_account_tiers` on create and update; reject it together
      with `assigned_account_ids`; drop blanks, duplicates and empty tiers.
- [x] Persist the tier index as `priority` through `replace_account_assignments`.
- [x] Return `assigned_account_tiers` grouped from the stored priority.
- [x] Build the proxy rank map from the tiers instead of list position.
- [x] Data migration: renumber legacy all-zero priorities in assignment order.
- [x] Dashboard: link/unlink an account to the rank above in the priority list,
      submit tiers, and detect changes ignoring order inside a tier.
- [x] Tests: API round trip and validation, persistence, migration, proxy route
      with a shared rank, selector balancing inside a rank, dashboard component
      and dialog behaviour.
- [x] Docs: account priority section in `docs/api-keys.md`.
