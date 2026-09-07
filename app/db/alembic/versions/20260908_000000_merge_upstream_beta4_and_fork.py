"""Merge upstream beta4 schema with deployed fork account-priority history."""

revision = "20260908_000000_merge_upstream_beta4_and_fork"
down_revision = (
    "20260827_020000_merge_retry_circuit_and_account_priority_heads",
    "20260830_000000_add_quota_warmup_claim_expiry",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
