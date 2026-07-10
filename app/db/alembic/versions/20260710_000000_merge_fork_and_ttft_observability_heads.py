"""Merge fork and TTFT observability heads.

Revision ID: 20260710_000000_merge_fork_and_ttft_observability_heads
Revises: 20260630_020000_merge_force_include_usage_and_upstream_sync_heads,
    20260709_000000_add_ttft_phase_observability
Create Date: 2026-07-10 00:00:00.000000
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "20260710_000000_merge_fork_and_ttft_observability_heads"
down_revision = (
    "20260630_020000_merge_force_include_usage_and_upstream_sync_heads",
    "20260709_000000_add_ttft_phase_observability",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
