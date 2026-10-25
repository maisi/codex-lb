from __future__ import annotations

import pytest

from app.core.config.settings import Settings

_ORACLE_URL = "oracle+oracledb://user:password@database.invalid/?service_name=service"


@pytest.fixture(autouse=True)
def no_pool_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODEX_LB_DATABASE_POOL_SIZE", raising=False)
    monkeypatch.delenv("CODEX_LB_DATABASE_MAX_OVERFLOW", raising=False)


def test_oracle_defaults_leave_capacity_for_both_pools_and_operations() -> None:
    settings = Settings(database_url=_ORACLE_URL, _env_file=None)
    assert settings.database_pool_size == 4
    assert settings.database_max_overflow == 0


@pytest.mark.parametrize("url", ["sqlite+aiosqlite:///:memory:", "postgresql+asyncpg://user:password@host/database"])
def test_other_backends_keep_existing_pool_defaults(url: str) -> None:
    settings = Settings(database_url=url, _env_file=None)
    assert settings.database_pool_size == 25
    assert settings.database_max_overflow == 15


@pytest.mark.parametrize("size,overflow", [(3, 1), (25, 15)])
def test_oracle_keeps_explicit_pool_values_even_when_matching_previous_defaults(size: int, overflow: int) -> None:
    settings = Settings(
        database_url=_ORACLE_URL, database_pool_size=size, database_max_overflow=overflow, _env_file=None
    )
    assert settings.database_pool_size == size
    assert settings.database_max_overflow == overflow


def test_oracle_keeps_pool_values_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEX_LB_DATABASE_URL", _ORACLE_URL)
    monkeypatch.setenv("CODEX_LB_DATABASE_POOL_SIZE", "6")
    monkeypatch.setenv("CODEX_LB_DATABASE_MAX_OVERFLOW", "2")
    settings = Settings(_env_file=None)
    assert settings.database_pool_size == 6
    assert settings.database_max_overflow == 2


def test_oracle_resolves_only_the_missing_pool_default() -> None:
    settings = Settings(database_url=_ORACLE_URL, database_pool_size=3, _env_file=None)
    assert settings.database_pool_size == 3
    assert settings.database_max_overflow == 0
    settings = Settings(database_url=_ORACLE_URL, database_max_overflow=1, _env_file=None)
    assert settings.database_pool_size == 4
    assert settings.database_max_overflow == 1
