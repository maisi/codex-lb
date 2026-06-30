"""Merge fork force_include_usage and upstream sync heads.

Revision ID: 20260630_020000_merge_force_include_usage_and_upstream_sync_heads
Revises: 20260624_000000_add_api_key_force_include_usage,
    20260630_010000_merge_warmup_and_request_log_dashboard_heads
Create Date: 2026-06-30 02:00:00.000000
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "20260630_020000_merge_force_include_usage_and_upstream_sync_heads"
down_revision = (
    "20260624_000000_add_api_key_force_include_usage",
    "20260630_010000_merge_warmup_and_request_log_dashboard_heads",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
