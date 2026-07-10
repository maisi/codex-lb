## Why

OAuth dialog copy actions can fail when the secure Clipboard API is unavailable
or blocked, because the `execCommand("copy")` fallback focuses a temporary
textarea outside the dialog focus trap. Operators need browser links, device
codes, and verification links to remain copyable in remote or non-secure
dashboard sessions.

## What Changes

- Scope clipboard fallback textareas to the triggering dialog when a copy action
  happens inside a dialog.
- Apply the fallback to browser authorization URLs, device user codes, and
  device verification URLs.
- Add regression coverage for OAuth dialog copy fallback paths.

## Impact

OAuth add-account flows remain usable when `navigator.clipboard.writeText` is
missing, blocked, or not available in the current browser context.
