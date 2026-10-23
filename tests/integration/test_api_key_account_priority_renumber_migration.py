"""Legacy all-zero assignment priorities become distinct ranks before tiers exist.

Ranks are read from ``api_key_accounts.priority`` and equal values mean "same
tier". Rows written before ranking existed all defaulted to 0, and the proxy
treated them as a waterfall in ``(priority, created_at)`` order; the migration
must keep that behavior instead of silently turning those keys into one tier.
"""

from __future__ import annotations

import pytest
from anyio import to_thread
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.migrate import run_upgrade

PARENT_REVISION = "20260929_000000_merge_upstream_post_beta9_and_fork"
TARGET_REVISION = "20261023_000000_renumber_api_key_account_priority"


@pytest.mark.asyncio
async def test_renumbers_legacy_zero_priorities_in_assignment_age_order(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'priority-renumber.sqlite'}"
    await to_thread.run_sync(lambda: run_upgrade(db_url, PARENT_REVISION, bootstrap_legacy=False))

    engine = create_async_engine(db_url, future=True)
    try:
        async with engine.begin() as conn:
            # Only the assignment table is read; SQLite leaves FK checks off here.
            await conn.execute(
                text(
                    "INSERT INTO api_key_accounts (api_key_id, account_id, priority, created_at) VALUES "
                    "('legacy', 'acc-newest', 0, '2026-08-03 00:00:00'), "
                    "('legacy', 'acc-oldest', 0, '2026-08-01 00:00:00'), "
                    "('legacy', 'acc-middle', 0, '2026-08-02 00:00:00'), "
                    "('ranked', 'acc-second', 1, '2026-09-01 00:00:00'), "
                    "('ranked', 'acc-first', 0, '2026-09-02 00:00:00'), "
                    "('gapped', 'acc-low', 7, '2026-09-01 00:00:00'), "
                    "('gapped', 'acc-high', 3, '2026-09-02 00:00:00')"
                )
            )

        await to_thread.run_sync(lambda: run_upgrade(db_url, TARGET_REVISION, bootstrap_legacy=False))

        async with engine.connect() as conn:
            rows = (await conn.execute(text("SELECT api_key_id, account_id, priority FROM api_key_accounts"))).all()
        ranks = {(api_key_id, account_id): priority for api_key_id, account_id, priority in rows}
        assert ranks == {
            ("legacy", "acc-oldest"): 0,
            ("legacy", "acc-middle"): 1,
            ("legacy", "acc-newest"): 2,
            ("ranked", "acc-first"): 0,
            ("ranked", "acc-second"): 1,
            # Distinct ranks are kept as stored, gaps included.
            ("gapped", "acc-high"): 3,
            ("gapped", "acc-low"): 7,
        }
    finally:
        await engine.dispose()
