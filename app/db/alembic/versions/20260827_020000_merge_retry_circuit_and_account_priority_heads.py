"""Merge the upstream retry-circuit chain and the account-priority head.

Revision ID: 20260827_020000_merge_retry_circuit_and_account_priority_heads
Revises:
- 20260827_000000_merge_retry_circuit_and_fork_heads
- 20260827_010000_add_api_key_account_priority
Create Date: 2026-08-27
"""

from __future__ import annotations

revision = "20260827_020000_merge_retry_circuit_and_account_priority_heads"
down_revision = (
    "20260827_000000_merge_retry_circuit_and_fork_heads",
    "20260827_010000_add_api_key_account_priority",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
