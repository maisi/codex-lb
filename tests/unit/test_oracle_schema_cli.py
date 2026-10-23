from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict

import pytest

import app.db.migrate as migrate
from app.db.oracle_schema import OracleSchemaBlocker, OracleSchemaBlockerKind, OracleSchemaReport


def _unexpected_database_use(*args, **kwargs):
    pytest.fail("Offline Oracle schema inventory must not load settings, a driver or a connection")


@pytest.mark.parametrize("as_json", [False, True])
def test_schema_cli_reports_full_inventory_before_settings_or_backend_guard(monkeypatch, capsys, as_json) -> None:
    report = OracleSchemaReport(
        table_count=2,
        blockers=(
            OracleSchemaBlocker(OracleSchemaBlockerKind.UNBOUNDED_STRING, "example", "key", "needs a size"),
            OracleSchemaBlocker(OracleSchemaBlockerKind.EMPTY_STRING_REPRESENTATION, "example", "key", "empty is NULL"),
            OracleSchemaBlocker(OracleSchemaBlockerKind.PARTIAL_INDEX, "example", "uq_key", "needs a predicate"),
        ),
    )
    monkeypatch.setattr(migrate, "inspect_oracle_schema", lambda: report)
    monkeypatch.setattr(migrate, "get_settings", _unexpected_database_use)
    monkeypatch.setattr(migrate, "create_engine", _unexpected_database_use)
    monkeypatch.setattr(migrate, "require_supported_database_backend", _unexpected_database_use)
    monkeypatch.setitem(sys.modules, "oracledb", None)
    monkeypatch.setattr(sys, "argv", ["codex-lb-db", "oracle-schema", *(["--json"] if as_json else [])])

    with pytest.raises(SystemExit) as exc_info:
        migrate.main()

    assert exc_info.value.code == 1
    output = capsys.readouterr()
    assert output.err == ""
    if as_json:
        payload = json.loads(output.out)
        assert payload == {
            "report_version": 1,
            "table_count": 2,
            "blocker_counts": {
                "unbounded_string": 1,
                "partial_index": 1,
                "empty_string_representation": 1,
            },
            "blockers": [asdict(blocker) for blocker in report.blockers],
            "database_connection": "not_attempted",
            "schema_mutation": "none",
            "oracle_runtime_support": "unsupported",
        }
    else:
        for expected in (
            "table_count=2",
            "unbounded_string=1",
            "partial_index=1",
            "empty_string_representation=1",
            "database_connection=not_attempted",
            "schema_mutation=none",
            "oracle_runtime_support=unsupported",
            "oracle_schema=blocked",
            "oracle-schema --json",
        ):
            assert expected in output.out


def test_schema_cli_empty_inventory_preserves_unsupported_runtime_and_zero_counts(monkeypatch, capsys) -> None:
    monkeypatch.setattr(migrate, "inspect_oracle_schema", lambda: OracleSchemaReport(table_count=0, blockers=()))
    monkeypatch.setattr(migrate, "get_settings", _unexpected_database_use)
    monkeypatch.setattr(sys, "argv", ["codex-lb-db", "oracle-schema", "--json"])

    migrate.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["blockers"] == []
    assert payload["table_count"] == 0
    assert payload["blocker_counts"] == {kind.value: 0 for kind in OracleSchemaBlockerKind}
    assert payload["oracle_runtime_support"] == "unsupported"


@pytest.mark.parametrize(
    "database_url", [None, "oracle+oracledb://operator:db-secret@db/?wallet_password=wallet-secret"]
)
@pytest.mark.parametrize("as_json", [False, True])
def test_schema_cli_subprocess_ignores_database_settings_and_never_imports_driver(database_url, as_json) -> None:
    env = os.environ.copy()
    env["CODEX_LB_DATABASE_POOL_SIZE"] = "invalid-and-unused"
    if database_url is None:
        env.pop("CODEX_LB_DATABASE_URL", None)
    else:
        env["CODEX_LB_DATABASE_URL"] = database_url
    script = """
import builtins
import sqlalchemy
original_import = builtins.__import__

def no_driver(name, *args, **kwargs):
    if name in {"oracledb", "app.db.session"}:
        raise AssertionError("database driver/session import reached")
    return original_import(name, *args, **kwargs)

def no_connection(*args, **kwargs):
    raise AssertionError("database connection reached")

builtins.__import__ = no_driver
sqlalchemy.create_engine = no_connection
from app.db.migrate import main
main()
"""

    result = subprocess.run(
        [sys.executable, "-c", script, "oracle-schema", *(["--json"] if as_json else [])],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )

    assert result.returncode == 1
    assert result.stderr == ""
    assert "Traceback" not in result.stdout
    assert "db-secret" not in result.stdout
    assert "wallet-secret" not in result.stdout
    if as_json:
        payload = json.loads(result.stdout)
        assert payload["table_count"] > 0
        assert payload["database_connection"] == "not_attempted"
        assert payload["schema_mutation"] == "none"
        assert payload["oracle_runtime_support"] == "unsupported"
        assert sum(payload["blocker_counts"].values()) == len(payload["blockers"]) > 0
    else:
        assert "oracle_schema=blocked" in result.stdout
        assert "offline metadata inventory" in result.stdout
