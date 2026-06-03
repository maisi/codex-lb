"""merge manual account routing and workspace/failure heads

Revision ID: 20260602_070000_merge_account_routing_and_workspace_heads
Revises:
    20260601_020000_merge_additional_quota_routing_and_relative_availability_heads,
    20260602_060000_merge_account_workspace_and_failure_heads
Create Date: 2026-06-02 07:00:00.000000
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "20260602_070000_merge_account_routing_and_workspace_heads"
down_revision = (
    "20260601_020000_merge_additional_quota_routing_and_relative_availability_heads",
    "20260602_060000_merge_account_workspace_and_failure_heads",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
