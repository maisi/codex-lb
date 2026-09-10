# Verification and scope

Upstream PR #2095 was cherry-picked with `-x`. All 164 pricing, API-key service and public Responses spend-cap regression tests passed. Ruff and formatting checks passed for touched Python files; repository type checking passed. The imported change passed strict OpenSpec validation.

The public regression verifies two Astra responses accrue $190 in API-equivalent long-context cost against a $100 cap and the next request is rejected before upstream dispatch. Canonical and dated Astra names both reserve nonzero budget and settle usage. Existing float-to-integer microdollar truncation is preserved, including the one-microdollar rounding difference for an 8,192-input/8,192-output reservation.

Per-surface Codex subscription pricing and GPT-6 request-suffix normalization remain outside this pricing-table change. No settings, dependency, migration, navigation or rendered dashboard layout changed.
