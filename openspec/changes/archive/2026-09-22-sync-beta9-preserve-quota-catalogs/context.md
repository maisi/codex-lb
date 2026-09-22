# Beta9 integration and quota-catalog incident

The September 22 incident involved owner-bound Astra continuations. Both Plus owners exhausted their five-hour quota while a business account retained 47% primary quota. The affected API key had account scoping disabled. Model refresh dropped Plus plan coverage, after which an unavailable-owner error became a model-policy conflict. Quota reset restored the model catalog.

The upgrade imports the exact beta9 release, including unavailable-owner retirement. The targeted fix keeps capability evidence separate from temporary capacity. It does not convert an unchanged account-bound delta into an account-neutral replay or bypass actual authorization changes.

For example, known Plus owner A reaches 100% quota while B remains healthy. A remains known to support Astra but cannot serve the request until quota recovers; the client receives an owner-unavailable response unless the existing recovery machinery proves that complete history can safely move. A removed model or changed plan still changes eligibility.

Validation must include the public continuation path, true model removal, all-known-accounts-exhausted refresh, reset recovery, snapshot roundtrip, and migration preservation. No new environment or dashboard setting is introduced.

The combined release also updates beta9's pinned Rust TLS dependency for
RUSTSEC-2026-0285, surfaced by the current dependency audit. Imported OpenSpec
deltas are reconciled with scenarios already present in the fork's canonical
specs, and upstream PostgreSQL warmup fixtures retain the fork's required
transition identities. These are integration corrections; no new operator
configuration or migration is required for them.
