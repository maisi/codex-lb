## MODIFIED Requirements

### Requirement: Accounts page

The Accounts page SHALL display a two-column layout: left panel with searchable account list, import button, and add account button; right panel with selected account details including usage, token info, and actions (pause/resume/delete/re-authenticate). The OAuth dialog SHALL show browser authorization URL, device user code, and device verification URL copy actions that remain functional in secure and non-secure contexts.

The Accounts page SHALL also allow exporting a selected account as an OpenCode-compatible `auth.json` payload with explicit raw-token warnings.

#### Scenario: OAuth add account

- **WHEN** a user clicks the add account button
- **THEN** an OAuth dialog opens with browser and device code flow options

#### Scenario: OAuth dialog copy fallback

- **WHEN** a user clicks Copy for the browser authorization URL, device user code, or device verification URL inside the OAuth dialog
- **THEN** the copy operation succeeds using secure Clipboard API when available
- **AND** falls back to dialog-scoped `execCommand("copy")` when secure Clipboard API is unavailable or blocked

#### Scenario: OAuth dialog copy failure feedback

- **WHEN** both clipboard copy paths fail for an OAuth dialog copy action
- **THEN** the dialog surfaces a visible copy failure message

#### Scenario: Device OAuth start begins polling

- **WHEN** the app starts Device Code OAuth with `POST /api/oauth/start`
- **AND** the response includes a `deviceAuthId` and `userCode`
- **THEN** the backend starts polling for the device token without requiring a separate `/api/oauth/complete` call
- **AND** a later `/api/oauth/complete` call remains safe and does not start a duplicate polling task
