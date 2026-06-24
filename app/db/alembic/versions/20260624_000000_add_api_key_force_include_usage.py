"""add api key force_include_usage flag

Revision ID: 20260624_000000_add_api_key_force_include_usage
Revises: 20260617_000000_merge_fork_main_and_upstream_sync_heads
Create Date: 2026-06-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

# revision identifiers, used by Alembic.
revision = "20260624_000000_add_api_key_force_include_usage"
down_revision = "20260617_000000_merge_fork_main_and_upstream_sync_heads"
branch_labels = None
depends_on = None


def _table_exists(connection: Connection, table_name: str) -> bool:
    inspector = sa.inspect(connection)
    return inspector.has_table(table_name)


def _columns(connection: Connection, table_name: str) -> set[str]:
    inspector = sa.inspect(connection)
    if not inspector.has_table(table_name):
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name) if column.get("name") is not None}


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "api_keys"):
        return

    existing_columns = _columns(bind, "api_keys")
    with op.batch_alter_table("api_keys") as batch_op:
        if "force_include_usage" not in existing_columns:
            batch_op.add_column(
                sa.Column(
                    "force_include_usage",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "api_keys"):
        return

    existing_columns = _columns(bind, "api_keys")
    with op.batch_alter_table("api_keys") as batch_op:
        if "force_include_usage" in existing_columns:
            batch_op.drop_column("force_include_usage")
