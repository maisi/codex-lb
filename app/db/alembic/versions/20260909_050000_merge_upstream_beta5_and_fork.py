"""Merge upstream beta5 dashboard schema with deployed fork history."""

revision = "20260909_050000_merge_upstream_beta5_and_fork"
down_revision = (
    "20260908_000000_merge_upstream_beta4_and_fork",
    "20260909_040000_dashboard_timeout_settings",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
