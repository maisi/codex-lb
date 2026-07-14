"""Merge fork and model-registry snapshot heads.

Revision ID: 20260714_000000_merge_fork_and_model_registry_heads
Revises: 20260710_000000_merge_fork_and_ttft_observability_heads,
    20260713_020000_add_model_registry_snapshot
Create Date: 2026-07-14 00:00:00.000000
"""

from __future__ import annotations

revision = "20260714_000000_merge_fork_and_model_registry_heads"
down_revision = (
    "20260710_000000_merge_fork_and_ttft_observability_heads",
    "20260713_020000_add_model_registry_snapshot",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
