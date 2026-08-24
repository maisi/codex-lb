"""Merge upstream v1.24.0-beta.4 and fork migration heads.

Revision ID: 20260824_000000_merge_v1_24_0_beta4_and_fork_heads
Revises:
- 20260813_000000_merge_v1_23_0_and_fork_heads
- 20260816_000000_add_model_source_embeddings
Create Date: 2026-08-24
"""

from __future__ import annotations

revision = "20260824_000000_merge_v1_24_0_beta4_and_fork_heads"
down_revision = (
    "20260813_000000_merge_v1_23_0_and_fork_heads",
    "20260816_000000_add_model_source_embeddings",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
