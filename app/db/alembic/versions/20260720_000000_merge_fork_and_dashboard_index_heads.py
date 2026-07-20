"""Merge fork and dashboard-index heads.

Revision ID: 20260720_000000_merge_fork_and_dashboard_index_heads
Revises: 20260714_000000_merge_fork_and_model_registry_heads,
    20260717_000000_optimize_dashboard_hot_path_indexes
Create Date: 2026-07-20 00:00:00.000000
"""

from __future__ import annotations

revision = "20260720_000000_merge_fork_and_dashboard_index_heads"
down_revision = (
    "20260714_000000_merge_fork_and_model_registry_heads",
    "20260717_000000_optimize_dashboard_hot_path_indexes",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
