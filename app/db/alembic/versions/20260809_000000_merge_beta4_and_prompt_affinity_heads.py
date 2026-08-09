"""Merge beta.4 and prompt-affinity migration heads.

Revision ID: 20260809_000000_merge_beta4_and_prompt_affinity_heads
Revises:
- 20260729_010000_add_api_key_prompt_cache_affinity_continuation
- 20260806_020000_add_usage_history_bulk_covering_indexes
Create Date: 2026-08-09
"""

from __future__ import annotations

revision = "20260809_000000_merge_beta4_and_prompt_affinity_heads"
down_revision = (
    "20260729_010000_add_api_key_prompt_cache_affinity_continuation",
    "20260806_020000_add_usage_history_bulk_covering_indexes",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
