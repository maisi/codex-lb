"""Merge fork-sync and weekly/monthly/useragent heads.

Revision ID: 20260608_000000_merge_fork_sync_and_weekly_monthly_heads
Revises:
- 20260604_180000_merge_reauth_and_fork_sync_heads
- 20260607_000000_merge_weekly_monthly_useragent_heads
Create Date: 2026-06-08 00:00:00.000000
"""

from __future__ import annotations

revision = "20260608_000000_merge_fork_sync_and_weekly_monthly_heads"
down_revision = (
    "20260604_180000_merge_reauth_and_fork_sync_heads",
    "20260607_000000_merge_weekly_monthly_useragent_heads",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
