"""Opt in with an isolated Oracle schema; the probe creates application data."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote, quote_plus

import pytest
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from app.core.runtime_logging import redact_rendered_log_text
from app.db.models import Base
from app.db.oracle_connection import create_oracle_sync_engine

_ORACLE_URL = os.environ.get("CODEX_LB_TEST_ORACLE_RUNTIME_URL", "")
_REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _ORACLE_URL, reason="Set CODEX_LB_TEST_ORACLE_RUNTIME_URL to an isolated owned Oracle schema."
    ),
]


def _safe_output(output: str | bytes | None) -> str:
    if output is None:
        return ""
    text = output.decode(errors="replace") if isinstance(output, bytes) else output
    url = make_url(_ORACLE_URL)
    secrets = {_ORACLE_URL, url.password, url.query.get("wallet_password")}
    for secret in secrets:
        if isinstance(secret, str) and secret:
            for variant in (secret, quote(secret, safe=""), quote_plus(secret)):
                text = text.replace(variant, "[REDACTED]")
    return redact_rendered_log_text(text)[-8000:]


@pytest.fixture
def empty_runtime_schema() -> Iterator[None]:
    engine = create_oracle_sync_engine(_ORACLE_URL)
    try:
        with engine.connect() as connection:
            if inspect(connection).get_table_names():
                pytest.fail("Oracle runtime smoke requires an empty owned schema; existing tables are preserved.")
        try:
            yield
        finally:
            with engine.begin() as connection:
                Base.metadata.drop_all(connection)
                if inspect(connection).has_table("alembic_version"):
                    connection.exec_driver_sql("DROP TABLE alembic_version PURGE")
    finally:
        engine.dispose()


def test_oracle_real_application_startup_persistence_restart_and_shutdown(
    tmp_path: Path, empty_runtime_schema: None
) -> None:
    pytest.importorskip("oracledb")
    # The child loads settings afresh and cannot inherit ambient production
    # settings, another test's SQLite override, credentials or repo .env files.
    allowed_environment = {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "TZ",
        "TMPDIR",
        "TEMP",
        "TMP",
        "SYSTEMROOT",
        "WINDIR",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "LD_LIBRARY_PATH",
    }
    environment = {key: value for key, value in os.environ.items() if key in allowed_environment}
    environment.update(
        {
            "CODEX_LB_DATABASE_URL": _ORACLE_URL,
            "CODEX_LB_DATA_DIR": str(tmp_path / "runtime-data"),
            "CODEX_LB_ENV_FILE": str(tmp_path / "missing.env"),
            "CODEX_LB_UPSTREAM_BASE_URL": "http://127.0.0.1:9/backend-api",
            "CODEX_LB_UPSTREAM_ROUTE_CACHE_TTL_SECONDS": "0",
            "CODEX_LB_TELEMETRY_ENABLED": "false",
            "CODEX_LB_METRICS_ENABLED": "false",
            "CODEX_LB_DASHBOARD_BOOTSTRAP_TOKEN": "oracle-smoke-bootstrap-only",
            "PYTHONPATH": str(_REPO_ROOT),
        }
    )
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("oracle_runtime_probe.py"))],
            cwd=_REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            "Oracle application probe exceeded its process deadline.\n"
            + _safe_output(exc.stdout)
            + "\n"
            + _safe_output(exc.stderr),
            pytrace=False,
        )
    if result.returncode:
        pytest.fail(
            f"Oracle application probe failed (exit={result.returncode}).\n"
            + _safe_output(result.stdout)
            + "\n"
            + _safe_output(result.stderr),
            pytrace=False,
        )
    for expected in (
        "oracle_application_startup_api_and_proxy_persistence=ok",
        "oracle_application_restart_and_shutdown=ok",
    ):
        if expected not in result.stdout:
            pytest.fail(
                "Oracle application probe did not confirm " + expected + ".\n" + _safe_output(result.stdout),
                pytrace=False,
            )
