"""Persist nullable execution provenance without rewriting request history."""

import sqlalchemy as sa
from alembic import op

revision = "20261101_000000_add_request_processing_node"
down_revision = "20261023_000000_renumber_api_key_account_priority"
branch_labels = None
depends_on = None


def _has_processing_node() -> bool:
    return any(column["name"] == "processing_node" for column in sa.inspect(op.get_bind()).get_columns("request_logs"))


def upgrade() -> None:
    if not _has_processing_node():
        op.add_column("request_logs", sa.Column("processing_node", sa.String(64), nullable=True))


def downgrade() -> None:
    if _has_processing_node():
        op.drop_column("request_logs", "processing_node")
