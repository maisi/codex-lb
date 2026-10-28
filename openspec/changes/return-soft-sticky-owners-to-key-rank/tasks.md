# Tasks

- [x] `StickyOwnerLookup.last_used_at`: the live row's `updated_at` for
      TTL-based kinds; none for durable lookups and legacy-shadowed owners.
- [x] Sticky selection: release a soft owner when it is `preserve` and a fresh
      pick is a different non-`preserve` account, or when the key ranks
      accounts, the owner is idle >= `PROMPT_CACHE_COLD_AFTER_SECONDS` (600 s)
      and a fresh pick holds a better rank. The fresh pick is seeded (no
      recovery-probe admission) and leaves no trace notes.
- [x] Routing trace owner flags `preserve_release` / `rank_return`; dashboard
      labels in en, ko and zh-CN.
- [x] Unit tests: preserve hand-back, preserve kept on the best rank or with no
      alternative, the 2026-10-28 production case, cold return, warm keep, no
      ranks, better rank unavailable, unknown last use; repository last-use
      test; end-to-end cold/warm test through `LoadBalancer.select_account`.
- [x] Docs: API key priority and soft sticky routing.
- [x] Strict OpenSpec validation.
