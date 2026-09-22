"""Merge the fork's beta6 head with the upstream beta9 head.

The upstream beta9 migration chain and the fork's later migration chain share
the same history through the earlier upstream/fork merges, but each ends in a
different head.  This revision is intentionally schema-neutral: it records
the convergence point without replaying either branch's operations.
"""

from __future__ import annotations

revision = "20260922_000000_merge_upstream_beta9_and_fork"
down_revision = (
    "20260909_080000_merge_upstream_beta6_and_fork",
    "20260913_000000_add_oidc_provider_flow",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Converge the two already-applied migration branches."""

    pass


def downgrade() -> None:
    """Re-expose both branch heads without changing their schemas."""

    pass
