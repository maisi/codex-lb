from __future__ import annotations

import io
import subprocess
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.db.migrate as migrate
import app.db.oracle_preflight as oracle

ORACLE_URL = (
    "oracle+oracledb://tester:private-db-password@database.invalid:1522/"
    "?service_name=service_tp&protocol=tcps&wallet_password=private-wallet-password"
)


def _cli(monkeypatch: pytest.MonkeyPatch, *args: str, url: str = ORACLE_URL) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["codex-lb-db", "--db-url", url, "oracle-check", "--pool-size", "4", "--max-overflow", "0", *args],
    )
    migrate.main()


def _worker_stub(monkeypatch: pytest.MonkeyPatch, *, failure: str | None = None) -> list[str]:
    events: list[str] = []

    class Params:
        def __init__(self, **kwargs):
            self.options = kwargs

        def set(self, **kwargs):
            self.options.update(kwargs)

    class Cursor:
        def __init__(self, mode: str):
            self.mode = mode

        def __enter__(self):
            return self

        def __exit__(self, *args):
            events.append(f"{self.mode}_cursor_closed")

        def execute(self, statement: str):
            events.append(statement)
            if failure == f"{self.mode}_query":
                print("driver stderr: private-wallet-password", file=sys.stderr)
                raise RuntimeError(SimpleNamespace(full_code="ORA-01017", message=ORACLE_URL))
            if failure == "unstructured_error":
                raise RuntimeError("wallet secret is ORA-54321")

        def fetchone(self):
            return (1,)

    class AsyncCursor(Cursor):
        async def execute(self, statement: str):
            super().execute(statement)

        async def fetchone(self):
            return super().fetchone()

    class Connection:
        version = "23.0.0.0.0"
        call_timeout = 0

        def __init__(self, mode: str):
            self.mode = mode

        def __enter__(self):
            events.append(f"{self.mode}_connected")
            return self

        def __exit__(self, *args):
            assert self.call_timeout > 0
            events.append(f"{self.mode}_closed")

        async def __aenter__(self):
            return self.__enter__()

        async def __aexit__(self, *args):
            self.__exit__(*args)

        def cursor(self):
            return AsyncCursor(self.mode) if self.mode == "async" else Cursor(self.mode)

    def connect(*, params):
        assert params.options["retry_count"] == 0
        assert params.options["tcp_connect_timeout"] == 10.0
        assert params.options["ssl_server_dn_match"] is True
        if failure == "sync_connect":
            raise RuntimeError(SimpleNamespace(full_code="DPY-6005", message=ORACLE_URL))
        return Connection("sync")

    fake_driver = SimpleNamespace(
        ConnectParams=Params,
        is_thin_mode=lambda: failure != "thick",
        connect=connect,
        connect_async=lambda **kwargs: Connection("async"),
    )
    monkeypatch.setitem(sys.modules, "oracledb", fake_driver)

    def run(command, *, input, **kwargs):
        assert command == [sys.executable, "-m", "app.db.oracle_preflight"]
        assert "private-db-password" not in " ".join(command)
        assert kwargs["timeout"] == 10.0
        stdout, stderr = io.StringIO(), io.StringIO()
        code = 0
        with monkeypatch.context() as worker_patch, redirect_stdout(stdout), redirect_stderr(stderr):
            worker_patch.setattr(sys, "stdin", io.StringIO(input))
            try:
                oracle._worker_main()
            except SystemExit as exc:
                assert isinstance(exc.code, int)
                code = exc.code
        return subprocess.CompletedProcess(command, code, stdout.getvalue(), stderr.getvalue())

    monkeypatch.setattr(oracle.subprocess, "run", run)
    return events


def test_cli_budget_two_replicas_and_update_reserve(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        oracle.subprocess, "run", lambda *args, **kwargs: pytest.fail("budget-only opened a connection")
    )

    _cli(monkeypatch, "--budget-only", "--replicas", "2", "--extra-replicas", "1", url="sqlite:///unused.db")

    output = capsys.readouterr().out
    assert "steady_sessions=16" in output
    assert "overlap_sessions=24" in output
    assert "remaining_sessions=6" in output
    assert "oracle_connection=not_checked" in output
    assert "oracle_runtime_support=single_instance" in output
    assert "not a throughput or HA guarantee" in output


def test_cli_uses_configured_pool_defaults_and_refuses_oversized_budget(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["codex-lb-db", "oracle-check", "--budget-only"])
    monkeypatch.setattr(
        migrate,
        "get_settings",
        lambda: SimpleNamespace(database_url=ORACLE_URL, database_pool_size=25, database_max_overflow=15),
    )
    monkeypatch.setattr(oracle.subprocess, "run", lambda *args, **kwargs: pytest.fail("oversized budget connected"))

    with pytest.raises(SystemExit, match="1"):
        migrate.main()

    output = capsys.readouterr().out
    assert "pool_size=25 max_overflow=15" in output
    assert "steady_sessions=80" in output
    assert "Deliberately lower pool size/overflow" in output


@pytest.mark.parametrize(
    "arguments",
    [
        ("--pool-size", "0"),
        ("--pool-size", "-1"),
        ("--max-overflow", "-1"),
        ("--replicas", "0"),
        ("--extra-replicas", "-1"),
        ("--session-limit", "0"),
        ("--session-limit", "8"),  # Exact capacity also leaves no reserve.
        ("--timeout-seconds", "0"),
        ("--timeout-seconds", "nan"),
        ("--timeout-seconds", "inf"),
        ("--timeout-seconds", "1e300"),
    ],
)
def test_cli_rejects_invalid_budgets_and_deadlines(monkeypatch, capsys, arguments) -> None:
    monkeypatch.setattr(oracle.subprocess, "run", lambda *args, **kwargs: pytest.fail("invalid preparation connected"))
    with pytest.raises(SystemExit, match="1"):
        _cli(monkeypatch, "--budget-only", *arguments)
    assert "oracle_preparation=failed" in capsys.readouterr().out


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user:private-db-password@host/database",
        "oracle+cx_oracle://user:private-db-password@host/database",
        "oracle+oracledb://user:private-db-password@host:bad/database",
        "oracle+oracledb://user:private-db-password@host:1521/",
        "oracle+oracledb://user:private-db-password@host/sid?service_name=service",
        "oracle+oracledb://user:private-db-password@host/?newpassword=private-wallet-password",
        "oracle+oracledb://user:private-db-password@host/?service_name=a&service_name=b",
    ],
)
def test_cli_rejects_invalid_or_unsafe_urls_without_credentials(monkeypatch, capsys, url) -> None:
    monkeypatch.setattr(oracle.subprocess, "run", lambda *args, **kwargs: pytest.fail("invalid URL connected"))
    with pytest.raises(SystemExit, match="1"):
        _cli(monkeypatch, url=url)
    output = capsys.readouterr()
    assert "oracle_preparation=failed" in output.out
    assert "private-db-password" not in output.out + output.err
    assert "private-wallet-password" not in output.out + output.err


def test_cli_checks_sync_async_thin_and_releases_every_resource(monkeypatch, capsys) -> None:
    events = _worker_stub(monkeypatch)
    _cli(monkeypatch)
    output = capsys.readouterr().out
    assert "oracle_sync_thin_connection=ok" in output
    assert "oracle_async_thin_connection=ok" in output
    assert "oracle_server_version=23.0.0.0.0" in output
    assert events == [
        "sync_connected",
        "SELECT 1 FROM DUAL",
        "sync_cursor_closed",
        "sync_closed",
        "async_connected",
        "SELECT 1 FROM DUAL",
        "async_cursor_closed",
        "async_closed",
    ]


@pytest.mark.parametrize("failure", ["sync_connect", "sync_query", "async_query", "thick"])
def test_cli_redacts_failures_and_releases_owned_connections(monkeypatch, capsys, failure) -> None:
    events = _worker_stub(monkeypatch, failure=failure)
    with pytest.raises(SystemExit, match="1"):
        _cli(monkeypatch)
    output = capsys.readouterr()
    assert "oracle_preparation=failed" in output.out
    assert "private-db-password" not in output.out + output.err
    assert "private-wallet-password" not in output.out + output.err
    if failure == "thick":
        assert "Thin mode" in output.out
    else:
        assert ("DPY-6005" if failure == "sync_connect" else "ORA-01017") in output.out
    if failure.endswith("query"):
        assert "sync_closed" in events
    if failure == "async_query":
        assert "async_closed" in events


def test_cli_timeout_does_not_forward_captured_output(monkeypatch, capsys) -> None:
    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"], output=b"private-db-password")

    monkeypatch.setattr(oracle.subprocess, "run", run)
    with pytest.raises(SystemExit, match="1"):
        _cli(monkeypatch)
    output = capsys.readouterr()
    assert "worker was stopped" in output.out
    assert "private-db-password" not in output.out + output.err


def test_cli_missing_driver_is_actionable(monkeypatch, capsys) -> None:
    _worker_stub(monkeypatch)
    monkeypatch.setitem(sys.modules, "oracledb", None)
    with pytest.raises(SystemExit, match="1"):
        _cli(monkeypatch)
    assert "uv sync --extra oracle" in capsys.readouterr().out


def test_cli_does_not_extract_error_codes_from_unstructured_exception_text(monkeypatch, capsys) -> None:
    _worker_stub(monkeypatch, failure="unstructured_error")
    with pytest.raises(SystemExit, match="1"):
        _cli(monkeypatch)
    output = capsys.readouterr()
    assert "Oracle connectivity failed" in output.out
    assert "ORA-54321" not in output.out + output.err


def test_cli_budget_is_usable_in_an_independent_process() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.db.migrate",
            "oracle-check",
            "--budget-only",
            "--pool-size",
            "4",
            "--max-overflow",
            "0",
            "--replicas",
            "2",
            "--extra-replicas",
            "1",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "remaining_sessions=6" in result.stdout


def test_real_worker_is_killed_and_reaped_on_deadline(monkeypatch, tmp_path: Path, capsys) -> None:
    # The stand-in process records its PID then hangs before any connection.
    script = tmp_path / "hung_worker.py"
    script.write_text(
        "import os, pathlib, time\n"
        "pathlib.Path(__file__).with_suffix('.pid').write_text(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )
    real_run = subprocess.run

    def run(command, **kwargs):
        return real_run([sys.executable, str(script)], **kwargs)

    monkeypatch.setattr(oracle.subprocess, "run", run)
    started = time.monotonic()
    with pytest.raises(SystemExit, match="1"):
        _cli(monkeypatch, "--timeout-seconds", "0.5")
    assert time.monotonic() - started < 5
    pid = (tmp_path / "hung_worker.pid").read_text()
    assert not Path(f"/proc/{pid}").exists()
    assert "timed out" in capsys.readouterr().out


def test_installed_driver_receives_autonomous_tls_configuration_without_connecting(tmp_path: Path) -> None:
    pytest.importorskip("oracledb")
    url = oracle._oracle_url(ORACLE_URL + "&config_dir=" + str(tmp_path) + "&wallet_location=" + str(tmp_path))
    params = oracle._connection_params(url, 3.0)

    assert params.host == "database.invalid"
    assert params.port == 1522
    assert params.service_name == "service_tp"
    assert params.protocol == "tcps"
    assert params.config_dir == str(tmp_path)
    assert params.wallet_location == str(tmp_path)
    assert params.ssl_server_dn_match is True
    assert params.tcp_connect_timeout == 3.0
    assert params.retry_count == 0


def test_installed_driver_tns_alias_cannot_override_deadline_or_tls_verification(tmp_path: Path) -> None:
    pytest.importorskip("oracledb")
    (tmp_path / "tnsnames.ora").write_text(
        "TEST_ALIAS = (DESCRIPTION=(RETRY_COUNT=20)(TRANSPORT_CONNECT_TIMEOUT=600)"
        "(ADDRESS=(PROTOCOL=tcps)(HOST=db.invalid)(PORT=1522))"
        "(CONNECT_DATA=(SERVICE_NAME=service_tp))(SECURITY=(SSL_SERVER_DN_MATCH=no)))"
    )
    url = oracle._oracle_url(f"oracle+oracledb://user:password@TEST_ALIAS?config_dir={tmp_path}")
    params = oracle._connection_params(url, 3.0)

    assert params.host == "db.invalid"
    assert params.port == 1522
    assert params.service_name == "service_tp"
    assert params.protocol == "tcps"
    assert params.ssl_server_dn_match is True
    assert params.tcp_connect_timeout == 3.0
    assert params.retry_count == 0
