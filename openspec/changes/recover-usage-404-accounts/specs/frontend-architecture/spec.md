## MODIFIED Requirements

### Requirement: Accounts page

The Accounts page SHALL display a two-column layout: left panel with searchable account list, import button, and add account button; right panel with selected account details including usage, token info, and actions (pause/resume/delete/re-authenticate). The browser OAuth stage SHALL show an authorization URL with a copy action that remains functional in secure and non-secure contexts.

The Accounts page SHALL allow Force probe for active, rate-limited, quota-exceeded, and usage-404-deactivated accounts. The Accounts page SHALL keep Force probe disabled for paused accounts, `reauth_required` accounts, and accounts deactivated for reasons other than usage HTTP 404.

#### Scenario: Usage-404-deactivated account can be force-probed

- **WHEN** a selected account has status `deactivated`
- **AND** its deactivation reason starts with `Usage API error: HTTP 404`
- **THEN** the Accounts page enables the Force probe action

#### Scenario: Other deactivated account cannot be force-probed

- **WHEN** a selected account has status `deactivated`
- **AND** its deactivation reason does not start with `Usage API error: HTTP 404`
- **THEN** the Accounts page disables the Force probe action
