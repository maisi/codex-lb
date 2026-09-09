"""Merge upstream beta6 schema with deployed fork history."""

revision = "20260909_080000_merge_upstream_beta6_and_fork"
down_revision = (
    "20260909_050000_merge_upstream_beta5_and_fork",
    "20260909_070000_automation_run_claim_budget",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
