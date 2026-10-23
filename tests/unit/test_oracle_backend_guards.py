from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

import app.db.migrate as migrate_module
import app.db.session as session_module
from app.db.backend_support import UnsupportedDatabaseBackendError, require_supported_database_backend

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ORACLE_URL = "oracle+oracledb://oracle_user:password-marker@127.0.0.1/service?wallet_password=wallet-marker"


def _unexpected_engine_creation(*args: object, **kwargs: object) -> None:
    pytest.fail("An incomplete Oracle backend must be rejected before engine creation")


@pytest.mark.parametrize(
    "driver", ["oracle", "oracle+oracledb", "oracle+cx_oracle", "oracle+unknown", "Oracle+ORACLEDB"]
)
def test_oracle_driver_variants_cannot_bypass_support_guard(driver: str) -> None:
    database_url = _ORACLE_URL.replace("oracle+oracledb", driver)

    with pytest.raises(UnsupportedDatabaseBackendError) as exc_info:
        require_supported_database_backend(database_url, operation="Application startup")

    message = str(exc_info.value)
    assert "application runtime and schema migrations are incomplete" in message
    assert "codex-lb-db oracle-check" in message
    assert "password-marker" not in message
    assert "wallet-marker" not in message
    assert "oracle_user" not in message


@pytest.mark.parametrize(
    "database_url",
    ["sqlite+aiosqlite:///:memory:", "sqlite:///store.db", "postgresql+asyncpg://user:password@localhost/database"],
)
def test_existing_backends_pass_support_guard(database_url: str) -> None:
    require_supported_database_backend(database_url, operation="Application startup")


@pytest.mark.parametrize("background", [False, True])
def test_oracle_runtime_engines_are_rejected_before_engine_creation(
    background: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(session_module, "create_async_engine", _unexpected_engine_creation)

    with pytest.raises(UnsupportedDatabaseBackendError, match="codex-lb-db oracle-check"):
        if background:
            session_module.init_background_db(_ORACLE_URL)
        else:
            session_module._create_main_engine(_ORACLE_URL)


@pytest.mark.parametrize("driver", ["oracle+oracledb", "oracle", "oracle+unknown"])
@pytest.mark.parametrize("entrypoint", ["module", "cli"])
def test_oracle_application_startup_fails_without_loading_a_driver(
    driver: str, entrypoint: str, tmp_path: Path
) -> None:
    env = os.environ.copy()
    env["CODEX_LB_DATABASE_URL"] = _ORACLE_URL.replace("oracle+oracledb", driver)
    env["CODEX_LB_DATA_DIR"] = str(tmp_path)
    script = """
import sqlalchemy.ext.asyncio

def reject_engine(*args, **kwargs):
    raise AssertionError("engine creation reached")

sqlalchemy.ext.asyncio.create_async_engine = reject_engine
"""
    if entrypoint == "cli":
        script += 'from app.cli import main\nmain(["--port", "0"])\n'
    else:
        script += "import app.main\n"

    result = subprocess.run(
        [sys.executable, "-c", script], cwd=_REPO_ROOT, env=env, capture_output=True, text=True, check=False, timeout=30
    )

    assert result.returncode != 0
    assert "application runtime and schema migrations are incomplete" in result.stderr
    assert "codex-lb-db oracle-check" in result.stderr
    assert "engine creation reached" not in result.stderr
    assert "NoSuchModuleError" not in result.stderr
    assert "password-marker" not in result.stderr
    assert "wallet-marker" not in result.stderr


@pytest.mark.parametrize("operation", ["upgrade", "stamp", "current", "check", "wait-for-connection", "wait-for-head"])
def test_oracle_migration_entrypoints_fail_before_engine_creation(
    operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(migrate_module, "create_engine", _unexpected_engine_creation)

    with pytest.raises(UnsupportedDatabaseBackendError, match="codex-lb-db oracle-check"):
        match operation:
            case "upgrade":
                migrate_module.run_upgrade(_ORACLE_URL, bootstrap_legacy=False)
            case "stamp":
                migrate_module.stamp_revision(_ORACLE_URL, "head")
            case "current":
                migrate_module.current_revision(_ORACLE_URL)
            case "check":
                migrate_module.check_schema_drift(_ORACLE_URL)
            case "wait-for-connection":
                migrate_module.wait_for_connection(_ORACLE_URL, timeout_seconds=1)
            case "wait-for-head":
                migrate_module.wait_for_head(_ORACLE_URL, timeout_seconds=1)
            case _:
                pytest.fail(f"Unhandled migration operation: {operation}")


@pytest.mark.parametrize("arguments", [["upgrade", "head"], ["stamp", "head"]])
@pytest.mark.parametrize("url_source", ["environment", "argument"])
def test_oracle_migration_cli_cannot_mutate_schema(arguments: list[str], url_source: str) -> None:
    env = os.environ.copy()
    if url_source == "environment":
        env["CODEX_LB_DATABASE_URL"] = _ORACLE_URL
        cli_arguments = arguments
    else:
        env["CODEX_LB_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
        cli_arguments = ["--db-url", _ORACLE_URL, *arguments]
    script = """
import sqlalchemy

def reject_engine(*args, **kwargs):
    raise AssertionError("engine creation reached")

sqlalchemy.create_engine = reject_engine
from app.db.migrate import main
main()
"""

    result = subprocess.run(
        [sys.executable, "-c", script, *cli_arguments],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode != 0
    assert "application runtime and schema migrations are incomplete" in result.stderr
    assert "codex-lb-db oracle-check" in result.stderr
    assert "engine creation reached" not in result.stderr
    assert "password-marker" not in result.stderr
    assert "wallet-marker" not in result.stderr


@pytest.mark.parametrize("offline", [False, True])
def test_direct_alembic_oracle_upgrade_is_rejected_before_engine_creation(
    offline: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sqlalchemy

    monkeypatch.setattr(sqlalchemy, "engine_from_config", _unexpected_engine_creation)
    config = Config()
    config.set_main_option("script_location", str(_REPO_ROOT / "app" / "db" / "alembic"))
    config.set_main_option("sqlalchemy.url", _ORACLE_URL)

    with pytest.raises(UnsupportedDatabaseBackendError, match="codex-lb-db oracle-check"):
        command.upgrade(config, "head", sql=offline)
