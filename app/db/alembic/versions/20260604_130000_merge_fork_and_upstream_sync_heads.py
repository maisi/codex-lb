"""Merge fork account routing and upstream proxy/quota planner heads.

Revision ID: 20260604_130000_merge_fork_and_upstream_sync_heads
Revises: 20260602_070000_merge_account_routing_and_workspace_heads,
    20260602_080000_merge_upstream_proxy_and_quota_planner_heads
Create Date: 2026-06-04 13:00:00.000000
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "20260604_130000_merge_fork_and_upstream_sync_heads"
down_revision = (
    "20260602_070000_merge_account_routing_and_workspace_heads",
    "20260602_080000_merge_upstream_proxy_and_quota_planner_heads",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
