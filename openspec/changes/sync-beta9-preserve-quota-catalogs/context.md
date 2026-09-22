# Beta9 integration and quota-catalog incident

The September 22 incident involved owner-bound Astra continuations. Both Plus owners exhausted their five-hour quota while a business account retained 47% primary quota. The affected API key had account scoping disabled. Model refresh dropped Plus plan coverage, after which an unavailable-owner error became a model-policy conflict. Quota reset restored the model catalog.

The upgrade imports the exact beta9 release, including unavailable-owner retirement. The targeted fix keeps capability evidence separate from temporary capacity. It does not convert an unchanged account-bound delta into an account-neutral replay or bypass actual authorization changes.

For example, known Plus owner A reaches 100% quota while B remains healthy. A remains known to support Astra but cannot serve the request until quota recovers; the client receives an owner-unavailable response unless the existing recovery machinery proves that complete history can safely move. A removed model or changed plan still changes eligibility.

Validation must include the public continuation path, true model removal, all-known-accounts-exhausted refresh, reset recovery, snapshot roundtrip, and migration preservation. No new environment or dashboard setting is introduced.
