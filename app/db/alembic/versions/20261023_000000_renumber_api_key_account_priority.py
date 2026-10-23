"""renumber per-API-key account priorities that predate explicit ranking

Revision ID: 20261023_000000_renumber_api_key_account_priority
Revises: 20260929_000000_merge_upstream_post_beta9_and_fork
Create Date: 2026-10-23

Assignments that existed before ``priority`` was added all defaulted to 0. The
proxy used to rank by list position, so those keys were a strict waterfall in
``(priority, created_at)`` order. Ranks are now read from ``priority`` itself,
where equal values mean "same tier", so give every key's assignments distinct
ranks in their current order first. Keys that already have distinct ranks keep
the same order.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

# revision identifiers, used by Alembic.
revision = "20261023_000000_renumber_api_key_account_priority"
down_revision = "20260929_000000_merge_upstream_post_beta9_and_fork"
branch_labels = None
depends_on = None


def _has_priority_column(connection: Connection) -> bool:
    inspector = sa.inspect(connection)
    if not inspector.has_table("api_key_accounts"):
        return False
    return any(column.get("name") == "priority" for column in inspector.get_columns("api_key_accounts"))


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_priority_column(bind):
        return

    rows = bind.execute(
        sa.text(
            "SELECT api_key_id, account_id, priority FROM api_key_accounts "
            "ORDER BY api_key_id, priority, created_at, account_id"
        )
    ).all()
    updates: list[dict[str, object]] = []
    rank = 0
    previous_key: str | None = None
    for api_key_id, account_id, priority in rows:
        rank = 0 if api_key_id != previous_key else rank + 1
        previous_key = api_key_id
        if priority != rank:
            updates.append({"api_key_id": api_key_id, "account_id": account_id, "priority": rank})
    if updates:
        bind.execute(
            sa.text(
                "UPDATE api_key_accounts SET priority = :priority "
                "WHERE api_key_id = :api_key_id AND account_id = :account_id"
            ),
            updates,
        )


def downgrade() -> None:
    # Distinct ranks are valid under the previous schema and keep its order.
    pass
