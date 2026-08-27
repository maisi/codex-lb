"""Merge the upstream retry-circuit head and the fork migration head.

Revision ID: 20260827_000000_merge_retry_circuit_and_fork_heads
Revises:
- 20260824_000000_merge_v1_24_0_beta4_and_fork_heads
- 20260821_000000_add_retry_circuit_admission_generation
Create Date: 2026-08-27
"""

from __future__ import annotations

revision = "20260827_000000_merge_retry_circuit_and_fork_heads"
down_revision = (
    "20260824_000000_merge_v1_24_0_beta4_and_fork_heads",
    "20260821_000000_add_retry_circuit_admission_generation",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
