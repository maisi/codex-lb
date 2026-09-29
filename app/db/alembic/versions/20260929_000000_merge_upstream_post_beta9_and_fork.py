"""Merge the fork's beta9 head with the upstream post-beta9 head.

Upstream added the SCIM token and subscription-overflow withdrawal revisions on
top of ``20260913_000000_add_oidc_provider_flow`` and converged them in
``20260918_000000_merge_scim_and_overflow_heads``.  The fork already built
``20260922_000000_merge_upstream_beta9_and_fork`` on the same parent.  This
revision is intentionally schema-neutral: it records the convergence point
without replaying either branch's operations.
"""

from __future__ import annotations

revision = "20260929_000000_merge_upstream_post_beta9_and_fork"
down_revision = (
    "20260922_000000_merge_upstream_beta9_and_fork",
    "20260918_000000_merge_scim_and_overflow_heads",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Converge the two already-applied migration branches."""

    pass


def downgrade() -> None:
    """Re-expose both branch heads without changing their schemas."""

    pass
