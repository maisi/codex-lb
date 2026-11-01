"""Add execution provenance after the immutable Oracle baseline.

Oracle DDL commits independently of the Alembic version stamp. Verify an
existing column before accepting a restart after interrupted DDL.
"""

from alembic import op
from sqlalchemy import text

from app.db.oracle_baseline import OracleSchemaDriftError

revision = "20261101_000100_request_node"
down_revision = "20261024_000000_oracle_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    existing = connection.execute(
        text(
            "SELECT data_type, data_length, char_used, nullable, data_default FROM user_tab_columns "
            "WHERE table_name = 'REQUEST_LOGS' AND column_name = 'PROCESSING_NODE'"
        )
    ).first()
    if existing is None:
        connection.exec_driver_sql("ALTER TABLE request_logs ADD (processing_node VARCHAR2(64 BYTE) NULL)")
    elif tuple(existing) != ("VARCHAR2", 64, "B", "Y", None):
        raise OracleSchemaDriftError("request_logs.processing_node: incompatible existing column")


def downgrade() -> None:
    op.drop_column("request_logs", "processing_node")
