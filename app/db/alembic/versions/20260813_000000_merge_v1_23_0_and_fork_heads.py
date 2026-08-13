"""Merge upstream v1.23.0 and fork migration heads.

Revision ID: 20260813_000000_merge_v1_23_0_and_fork_heads
Revises:
- 20260806_120000_add_http_bridge_owner_process_epoch
- 20260809_000000_merge_beta4_and_prompt_affinity_heads
Create Date: 2026-08-13
"""

from __future__ import annotations

revision = "20260813_000000_merge_v1_23_0_and_fork_heads"
down_revision = (
    "20260806_120000_add_http_bridge_owner_process_epoch",
    "20260809_000000_merge_beta4_and_prompt_affinity_heads",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
