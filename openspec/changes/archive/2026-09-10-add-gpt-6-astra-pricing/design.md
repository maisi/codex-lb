# Design

Cherry-pick upstream PR #2095, commit `94fc99b6937b6d23a03cf2d91344cbff5ca133a8`, preserving author attribution. Use the existing ModelPrice entry, service-tier selection, long-context threshold and snapshot alias mechanism. No new configuration, schema or billing surface is introduced.

Keep API-equivalent rates rather than introducing Codex-specific subscription accounting. Preserve the existing microdollar conversion when reserving budgets. Extend existing reservation and public Responses spend-cap tests to Astra; retain the original GPT-5.6 alias assertion.
