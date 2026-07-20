"""Deduplicate limit warm-up attempts by observed transition.

Revision ID: 20260715_000000_add_warmup_transition_key
Revises: 20260710_000000_merge_fork_and_ttft_observability_heads
Create Date: 2026-07-15 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260715_000000_add_warmup_transition_key"
down_revision = "20260710_000000_merge_fork_and_ttft_observability_heads"
branch_labels = None
depends_on = None

_TABLE = "account_limit_warmups"
_OLD_UNIQUE = "uq_account_limit_warmups_account_window_reset"
_NEW_UNIQUE = "uq_account_limit_warmups_account_window_transition"


def _columns() -> dict[str, dict[str, object]]:
    return {
        str(column["name"]): dict(column)
        for column in sa.inspect(op.get_bind()).get_columns(_TABLE)
        if column.get("name") is not None
    }


def _unique_constraints() -> set[str]:
    return {
        str(constraint["name"])
        for constraint in sa.inspect(op.get_bind()).get_unique_constraints(_TABLE)
        if constraint.get("name") is not None
    }


def upgrade() -> None:
    columns = _columns()
    if "transition_key" not in columns:
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.add_column(sa.Column("transition_key", sa.String(), nullable=True))

    op.execute(
        sa.text(
            "UPDATE account_limit_warmups "
            "SET transition_key = 'legacy-reset:' || CAST(reset_at AS VARCHAR) "
            "WHERE transition_key IS NULL"
        )
    )

    columns = _columns()
    unique_constraints = _unique_constraints()
    with op.batch_alter_table(_TABLE) as batch_op:
        if _OLD_UNIQUE in unique_constraints:
            batch_op.drop_constraint(_OLD_UNIQUE, type_="unique")
        if bool(columns["transition_key"].get("nullable", True)):
            batch_op.alter_column(
                "transition_key",
                existing_type=sa.String(),
                nullable=False,
            )
        if _NEW_UNIQUE not in unique_constraints:
            batch_op.create_unique_constraint(
                _NEW_UNIQUE,
                ["account_id", "window", "transition_key"],
            )


def downgrade() -> None:
    columns = _columns()
    unique_constraints = _unique_constraints()
    if _NEW_UNIQUE in unique_constraints:
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.drop_constraint(_NEW_UNIQUE, type_="unique")

    # The old schema cannot represent multiple observed transitions with the
    # same reset deadline. Retain the earliest attempt for each legacy tuple.
    op.execute(
        sa.text(
            "DELETE FROM account_limit_warmups "
            "WHERE id NOT IN ("
            "SELECT MIN(id) FROM account_limit_warmups "
            "GROUP BY account_id, window, reset_at"
            ")"
        )
    )

    unique_constraints = _unique_constraints()
    with op.batch_alter_table(_TABLE) as batch_op:
        if _OLD_UNIQUE not in unique_constraints:
            batch_op.create_unique_constraint(
                _OLD_UNIQUE,
                ["account_id", "window", "reset_at"],
            )
        if "transition_key" in columns:
            batch_op.drop_column("transition_key")
