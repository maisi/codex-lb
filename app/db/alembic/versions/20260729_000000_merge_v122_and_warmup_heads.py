"""Merge v1.22 request-log and fork warm-up migration heads.

Revision ID: 20260729_000000_merge_v122_and_warmup_heads
Revises: 20260720_010000_merge_warmup_transition_and_dashboard_index_heads,
20260722_000000_backfill_request_log_useragent_families
Create Date: 2026-07-29 00:00:00.000000
"""

from __future__ import annotations

revision = "20260729_000000_merge_v122_and_warmup_heads"
down_revision = (
    "20260720_010000_merge_warmup_transition_and_dashboard_index_heads",
    "20260722_000000_backfill_request_log_useragent_families",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
