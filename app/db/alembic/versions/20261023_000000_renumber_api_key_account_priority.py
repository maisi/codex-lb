"""renumber per-API-key account priorities that predate explicit ranking

Revision ID: 20261023_000000_renumber_api_key_account_priority
Revises: 20260929_000000_merge_upstream_post_beta9_and_fork
Create Date: 2026-10-23

Assignments that existed before ``priority`` was added all defaulted to 0. The
proxy used to rank by list position, so those keys were a strict waterfall in
``(priority, created_at)`` order. Ranks are now read from ``priority`` itself,
where equal values mean "same tier", so give the assignments of every key that
shares a value distinct ranks in their current order first. Keys whose ranks are
already distinct are left untouched.
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
    assignments_by_key: dict[str, list[tuple[str, int]]] = {}
    for api_key_id, account_id, priority in rows:
        assignments_by_key.setdefault(api_key_id, []).append((account_id, priority))
    updates: list[dict[str, object]] = []
    for api_key_id, assignments in assignments_by_key.items():
        # Only shared values predate ranking; distinct ranks are left exactly as stored.
        if len({priority for _, priority in assignments}) == len(assignments):
            continue
        for rank, (account_id, _) in enumerate(assignments):
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
