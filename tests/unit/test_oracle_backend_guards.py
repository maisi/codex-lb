from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

import app.db.migrate as migrate_module
import app.db.session as session_module
from app.db.backend_support import UnsupportedDatabaseBackendError, require_supported_database_backend

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ORACLE_URL = "oracle+oracledb://oracle_user:password-marker@127.0.0.1/service?wallet_password=wallet-marker"


@pytest.mark.parametrize("driver", ["oracle", "oracle+cx_oracle", "oracle+unknown", "Oracle+ORACLEDB"])
def test_oracle_unverified_driver_variants_fail_without_exposing_credentials(driver: str) -> None:
    with pytest.raises(UnsupportedDatabaseBackendError) as error:
        require_supported_database_backend(
            _ORACLE_URL.replace("oracle+oracledb", driver), operation="Application startup"
        )
    message = str(error.value)
    assert "native oracle+oracledb:// Thin driver" in message
    assert "codex-lb-db oracle-check" in message
    assert all(secret not in message for secret in ("password-marker", "wallet-marker", "oracle_user"))


@pytest.mark.parametrize("url", [_ORACLE_URL, "sqlite+aiosqlite:///:memory:", "postgresql+asyncpg://u:p@localhost/db"])
def test_supported_database_drivers_pass_without_connecting(url: str) -> None:
    require_supported_database_backend(url, operation="Application startup")


def test_oracle_request_engine_uses_native_runtime_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[str] = []
    expected = session_module.engine

    def build(url: str):
        observed.append(url)
        return expected

    monkeypatch.setattr(session_module, "_create_oracle_engine", build)
    assert session_module._create_main_engine(_ORACLE_URL) is expected
    assert observed == [_ORACLE_URL]


def test_oracle_stamp_cannot_skip_installation_or_contact_database(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(*args, **kwargs):
        pytest.fail("Oracle stamp reached the database instead of requiring a verified baseline")

    monkeypatch.setattr(migrate_module, "_build_alembic_config", reject)
    with pytest.raises(UnsupportedDatabaseBackendError, match="Stamping Oracle schemas is disabled"):
        migrate_module.stamp_revision(_ORACLE_URL, "head")


@pytest.mark.parametrize("offline", [False, True])
def test_oracle_cannot_replay_the_sqlite_postgresql_alembic_history(
    offline: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sqlalchemy

    def reject(*args, **kwargs):
        pytest.fail("Oracle reached the historical SQLite/PostgreSQL engine")

    monkeypatch.setattr(sqlalchemy, "engine_from_config", reject)
    config = Config()
    config.set_main_option("script_location", str(_REPO_ROOT / "app" / "db" / "alembic"))
    config.set_main_option("sqlalchemy.url", _ORACLE_URL)
    with pytest.raises(UnsupportedDatabaseBackendError, match="dedicated Alembic baseline"):
        command.upgrade(config, "head", sql=offline)
