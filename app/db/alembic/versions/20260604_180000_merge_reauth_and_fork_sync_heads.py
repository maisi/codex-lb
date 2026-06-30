"""Merge reauth-required and fork upstream-sync heads.

Revision ID: 20260604_180000_merge_reauth_and_fork_sync_heads
Revises: 20260604_000000_add_reauth_required_account_status,
    20260604_130000_merge_fork_and_upstream_sync_heads
Create Date: 2026-06-04 18:00:00.000000
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "20260604_180000_merge_reauth_and_fork_sync_heads"
down_revision = (
    "20260604_000000_add_reauth_required_account_status",
    "20260604_130000_merge_fork_and_upstream_sync_heads",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
