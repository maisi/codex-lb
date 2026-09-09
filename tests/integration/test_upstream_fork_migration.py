from __future__ import annotations

from pathlib import Path

import pytest
from anyio import to_thread
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.migrate import run_upgrade

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "parent",
    [
        "20260827_020000_merge_retry_circuit_and_account_priority_heads",
        "20260830_000000_add_quota_warmup_claim_expiry",
        "20260908_000000_merge_upstream_beta4_and_fork",
        "20260909_040000_dashboard_timeout_settings",
        "20260909_050000_merge_upstream_beta5_and_fork",
        "20260909_070000_automation_run_claim_budget",
    ],
)
async def test_upstream_fork_merge_preserves_existing_key_policy(tmp_path: Path, parent: str) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'merge.db'}"
    await to_thread.run_sync(lambda: run_upgrade(database_url, parent, bootstrap_legacy=True))
    engine = create_async_engine(database_url)
    is_fork = "account_priority" in parent or "merge_upstream_beta" in parent
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO api_keys (id, name, key_hash, key_prefix, is_active) "
                    "VALUES ('existing-key', 'Existing key', 'existing-hash', 'sk-existing', true)"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO accounts (id, codex_installation_id, email, plan_type, "
                    "access_token_encrypted, refresh_token_encrypted, id_token_encrypted, last_refresh, status) "
                    "VALUES ('existing-account', '00000000-0000-4000-8000-000000000001', "
                    "'migration@example.com', 'plus', X'01', X'02', X'03', CURRENT_TIMESTAMP, 'active')"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO api_key_accounts (api_key_id, account_id) VALUES ('existing-key', 'existing-account')"
                )
            )
            if is_fork:
                await connection.execute(
                    text("UPDATE api_key_accounts SET priority = 7 WHERE api_key_id = 'existing-key'")
                )
                await connection.execute(
                    text(
                        "UPDATE api_keys SET force_include_usage = true, "
                        "prompt_cache_affinity_continuation = true WHERE id = 'existing-key'"
                    )
                )
        await to_thread.run_sync(lambda: run_upgrade(database_url, "head", bootstrap_legacy=False))
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "SELECT force_include_usage, prompt_cache_affinity_continuation "
                        "FROM api_keys WHERE id = 'existing-key'"
                    )
                )
            ).one()
            assert tuple(bool(value) for value in row) == (is_fork, is_fork)
            priority = (
                await connection.execute(
                    text("SELECT priority FROM api_key_accounts WHERE api_key_id = 'existing-key'")
                )
            ).scalar_one()
            assert priority == (7 if is_fork else 0)
            revisions = (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
            assert revisions == ["20260909_080000_merge_upstream_beta6_and_fork"]
    finally:
        await engine.dispose()
