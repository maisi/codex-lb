"""Merge fork main and upstream-sync heads.

Revision ID: 20260617_000000_merge_fork_main_and_upstream_sync_heads
Revises:
- 20260608_000000_merge_fork_sync_and_weekly_monthly_heads
- 20260611_000000_merge_dashboard_guest_and_weekly_useragent_heads
Create Date: 2026-06-17 00:00:00.000000
"""

from __future__ import annotations

revision = "20260617_000000_merge_fork_main_and_upstream_sync_heads"
down_revision = (
    "20260608_000000_merge_fork_sync_and_weekly_monthly_heads",
    "20260611_000000_merge_dashboard_guest_and_weekly_useragent_heads",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
