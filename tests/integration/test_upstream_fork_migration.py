from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from anyio import to_thread
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.migrate import _build_alembic_config, run_upgrade

pytestmark = pytest.mark.integration
_FORK_HEAD = "20260909_080000_merge_upstream_beta6_and_fork"
_UPSTREAM_BETA9_HEAD = "20260913_000000_add_oidc_provider_flow"
_MERGE_HEAD = "20260922_000000_merge_upstream_beta9_and_fork"


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
        _FORK_HEAD,
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
            assert revisions == [_MERGE_HEAD]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_populated_upstream_beta9_head_reaches_merged_head(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'beta9.db'}"
    await to_thread.run_sync(lambda: run_upgrade(database_url, _UPSTREAM_BETA9_HEAD, bootstrap_legacy=True))
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            providers_before = (
                await connection.execute(text("SELECT COUNT(*) FROM dashboard_auth_providers"))
            ).scalar_one()
            assert providers_before >= 1

        await to_thread.run_sync(lambda: run_upgrade(database_url, "head", bootstrap_legacy=False))

        async with engine.connect() as connection:
            providers_after = (
                await connection.execute(text("SELECT COUNT(*) FROM dashboard_auth_providers"))
            ).scalar_one()
            assert providers_after == providers_before
            assert (await connection.execute(text("SELECT COUNT(*) FROM dashboard_oidc_login_flows"))).scalar_one() == 0
            revisions = (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
            assert revisions == [_MERGE_HEAD]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_merge_round_trip_preserves_auth_and_continuity_rows(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'roundtrip.db'}"
    await to_thread.run_sync(lambda: run_upgrade(database_url, "head", bootstrap_legacy=True))
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO dashboard_roles (id, slug, name, kind) "
                    "VALUES ('synthetic-role', 'synthetic', 'Synthetic role', 'custom')"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO dashboard_role_grants (role_id, permission, scope) "
                    "VALUES ('synthetic-role', 'dashboard:read', 'own')"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO dashboard_auth_providers (id, kind, provider_key, label) "
                    "VALUES ('synthetic-provider', 'oidc', 'synthetic', 'Synthetic provider')"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO http_bridge_sessions ("
                    "id, session_key_kind, session_key_value, session_key_hash, api_key_scope, "
                    "owner_instance_id, owner_epoch, state, model, latest_turn_state, latest_response_id"
                    ") VALUES ("
                    "'synthetic-session', 'session_header', 'continuity-key', 'continuity-hash', 'scope', "
                    "'instance', 4, 'active', 'gpt-5.6', 'turn-state', 'response-id'"
                    ")"
                )
            )

        async with engine.connect() as connection:
            before = {
                "roles": (
                    await connection.execute(
                        text("SELECT id, slug, name, kind FROM dashboard_roles WHERE id = 'synthetic-role'")
                    )
                ).all(),
                "grants": (
                    await connection.execute(
                        text(
                            "SELECT role_id, permission, scope FROM dashboard_role_grants "
                            "WHERE role_id = 'synthetic-role'"
                        )
                    )
                ).all(),
                "providers": (
                    await connection.execute(
                        text(
                            "SELECT id, kind, provider_key, label FROM dashboard_auth_providers "
                            "WHERE id = 'synthetic-provider'"
                        )
                    )
                ).all(),
                "continuity": (
                    await connection.execute(
                        text(
                            "SELECT id, session_key_hash, owner_epoch, state, model, latest_turn_state, "
                            "latest_response_id FROM http_bridge_sessions WHERE id = 'synthetic-session'"
                        )
                    )
                ).all(),
            }

        await to_thread.run_sync(
            lambda: command.downgrade(_build_alembic_config(database_url), _FORK_HEAD),
        )

        async with engine.connect() as connection:
            revisions_after_downgrade = (
                (await connection.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num")))
                .scalars()
                .all()
            )
            assert revisions_after_downgrade == [_FORK_HEAD, _UPSTREAM_BETA9_HEAD]
            assert (
                await connection.execute(
                    text("SELECT id, slug, name, kind FROM dashboard_roles WHERE id = 'synthetic-role'")
                )
            ).all() == before["roles"]
            assert (
                await connection.execute(
                    text(
                        "SELECT role_id, permission, scope FROM dashboard_role_grants WHERE role_id = 'synthetic-role'"
                    )
                )
            ).all() == before["grants"]
            provider_rows = (
                await connection.execute(
                    text(
                        "SELECT id, kind, provider_key, label FROM dashboard_auth_providers "
                        "WHERE id = 'synthetic-provider'"
                    )
                )
            ).all()
            assert provider_rows == before["providers"]
            continuity_rows = (
                await connection.execute(
                    text(
                        "SELECT id, session_key_hash, owner_epoch, state, model, latest_turn_state, "
                        "latest_response_id FROM http_bridge_sessions WHERE id = 'synthetic-session'"
                    )
                )
            ).all()
            assert continuity_rows == before["continuity"]

        result = await to_thread.run_sync(lambda: run_upgrade(database_url, "head", bootstrap_legacy=False))
        assert result.current_revision == _MERGE_HEAD
    finally:
        await engine.dispose()


def test_beta9_fork_migration_graph_converges_to_one_head(tmp_path: Path) -> None:
    config = _build_alembic_config(f"sqlite+aiosqlite:///{tmp_path / 'graph.db'}")
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == [_MERGE_HEAD]
    merge = script.get_revision(_MERGE_HEAD)
    assert merge is not None
    assert merge.down_revision == (_FORK_HEAD, _UPSTREAM_BETA9_HEAD)
