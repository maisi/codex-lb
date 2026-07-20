"""Merge warm-up transition and dashboard-index migration heads.

Revision ID: 20260720_010000_merge_warmup_transition_and_dashboard_index_heads
Revises: 20260715_000000_add_warmup_transition_key, 20260720_000000_merge_fork_and_dashboard_index_heads
Create Date: 2026-07-20 01:00:00.000000
"""

from __future__ import annotations

revision = "20260720_010000_merge_warmup_transition_and_dashboard_index_heads"
down_revision = (
    "20260715_000000_add_warmup_transition_key",
    "20260720_000000_merge_fork_and_dashboard_index_heads",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
