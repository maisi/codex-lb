"""Create the first Oracle schema from its immutable, revision-pinned snapshot.

Revision ID: 20261024_000000_oracle_baseline
Revises: None
"""

from alembic import op

from app.db.oracle_baseline import apply_oracle_baseline

revision = "20261024_000000_oracle_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    apply_oracle_baseline(op.get_bind())


def downgrade() -> None:
    raise RuntimeError("The initial Oracle baseline cannot be downgraded; use a disposable schema for reset")
