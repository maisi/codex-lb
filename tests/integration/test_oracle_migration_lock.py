"""Opt-in cross-process mutex tests on an owned Oracle test database."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.pool import NullPool

import app.db.migration_lock as lock_module
from app.db.migration_lock import migration_lock

_ORACLE_URL = os.environ.get("CODEX_LB_TEST_ORACLE_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _ORACLE_URL, reason="Set CODEX_LB_TEST_ORACLE_URL to an owned Oracle test schema."),
]
_WORKER = """
import os
import sys
import time
from pathlib import Path
import app.db.migration_lock as locking

ready, release, guard = map(Path, sys.argv[1:4])
mode, timeout = sys.argv[4], float(sys.argv[5])
acquire_with_timeout = locking._acquire_with_timeout

def observe_acquisition(try_acquire, **kwargs):
    def observed_try():
        acquired = try_acquire()
        if not acquired:
            ready.with_suffix('.waiting').touch()
        return acquired
    return acquire_with_timeout(observed_try, **kwargs)

locking._acquire_with_timeout = observe_acquisition
try:
    with locking.migration_lock(os.environ['CODEX_LB_TEST_ORACLE_URL'], timeout_seconds=timeout):
        if mode == 'exclusive':
            with guard.open('x'):
                pass
        ready.touch()
        try:
            deadline = time.monotonic() + 20
            while not release.exists():
                if time.monotonic() >= deadline:
                    raise RuntimeError('test body release deadline exceeded')
                time.sleep(0.02)
            if mode == 'exception':
                raise ValueError('expected test body failure')
        finally:
            if mode == 'exclusive':
                guard.unlink()
    print('released', flush=True)
except TimeoutError:
    print('timeout', flush=True)
    sys.exit(4)
except ValueError:
    if mode != 'exception':
        raise
    print('body_failure_released', flush=True)
except BaseException as exc:
    print('worker_failure=' + type(exc).__name__, flush=True)
    sys.exit(3)
"""


@pytest.fixture(autouse=True)
def require_oracle_driver() -> None:
    pytest.importorskip("oracledb")
    assert make_url(_ORACLE_URL).drivername == "oracle+oracledb"


@pytest.fixture
def processes() -> Iterator[list[subprocess.Popen[str]]]:
    children: list[subprocess.Popen[str]] = []
    try:
        yield children
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=10)
            if child.stdout is not None:
                child.stdout.close()
            if child.stderr is not None:
                child.stderr.close()


def _spawn(
    processes: list[subprocess.Popen[str]],
    ready: Path,
    release: Path,
    *,
    mode: str = "hold",
    timeout: float = 10,
    guard: Path | None = None,
) -> subprocess.Popen[str]:
    child = subprocess.Popen(
        [sys.executable, "-c", _WORKER, str(ready), str(release), str(guard or ready), mode, str(timeout)],
        env={**os.environ, "CODEX_LB_TEST_ORACLE_URL": _ORACLE_URL},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    processes.append(child)
    return child


def _wait_for_marker(child: subprocess.Popen[str], marker: Path) -> None:
    deadline = time.monotonic() + 15
    while not marker.exists():
        if child.poll() is not None:
            pytest.fail(f"Oracle mutex worker exited before its synchronization marker: exit={child.returncode}")
        if time.monotonic() >= deadline:
            pytest.fail("Oracle mutex worker did not reach its synchronization marker before the test deadline")
        time.sleep(0.02)


def _completed(child: subprocess.Popen[str], expected: str, *, code: int = 0) -> None:
    stdout, stderr = child.communicate(timeout=15)
    password = make_url(_ORACLE_URL).password
    if password and (password in stdout or password in stderr):
        pytest.fail("Oracle mutex worker exposed a credential; captured output has been withheld")
    assert child.returncode == code, f"Oracle mutex worker exit={child.returncode} output={stdout.strip()}"
    assert stdout.strip() == expected


def test_oracle_mutex_serializes_two_migration_processes(
    processes: list[subprocess.Popen[str]], tmp_path: Path
) -> None:
    first_ready, second_ready = tmp_path / "first.ready", tmp_path / "second.ready"
    first_release, second_release = tmp_path / "first.release", tmp_path / "second.release"
    guard = tmp_path / "exclusive-body"
    first = _spawn(processes, first_ready, first_release, mode="exclusive", guard=guard)
    _wait_for_marker(first, first_ready)
    second = _spawn(processes, second_ready, second_release, mode="exclusive", guard=guard)
    _wait_for_marker(second, second_ready.with_suffix(".waiting"))
    assert not second_ready.exists()
    first_release.touch()
    _completed(first, "released")
    _wait_for_marker(second, second_ready)
    second_release.touch()
    _completed(second, "released")
    assert not guard.exists()


def test_oracle_mutex_times_out_another_process_without_entering_body(
    processes: list[subprocess.Popen[str]], tmp_path: Path
) -> None:
    ready = tmp_path / "contender.ready"
    with migration_lock(_ORACLE_URL, timeout_seconds=5):
        started = time.monotonic()
        contender = _spawn(processes, ready, tmp_path / "release", timeout=0.25)
        _completed(contender, "timeout", code=4)
        assert time.monotonic() - started < 10
        assert not ready.exists()
    with migration_lock(_ORACLE_URL, timeout_seconds=5):
        pass


def test_oracle_mutex_survives_schema_commits_on_another_connection(
    processes: list[subprocess.Popen[str]], tmp_path: Path
) -> None:
    name = f"codex_lock_{uuid4().hex[:12]}"
    engine = create_engine(_ORACLE_URL, poolclass=NullPool, hide_parameters=True)
    created = False
    try:
        with migration_lock(_ORACLE_URL, timeout_seconds=5):
            with engine.begin() as connection:
                connection.execute(text(f"CREATE TABLE {name} (id NUMBER PRIMARY KEY)"))
                created = True
                connection.execute(text(f"INSERT INTO {name} (id) VALUES (1)"))
            contender = _spawn(processes, tmp_path / "contender.ready", tmp_path / "release", timeout=0.25)
            _completed(contender, "timeout", code=4)
            assert not (tmp_path / "contender.ready").exists()
            with engine.connect() as connection:
                assert connection.scalar(text(f"SELECT COUNT(*) FROM {name}")) == 1
        with migration_lock(_ORACLE_URL, timeout_seconds=5):
            pass
    finally:
        try:
            if created:
                with engine.begin() as connection:
                    connection.execute(text(f"DROP TABLE {name} PURGE"))
        finally:
            engine.dispose()


def test_oracle_mutex_survives_commit_on_its_own_connection(
    processes: list[subprocess.Popen[str]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connections: list[Connection] = []

    def observe_engine(url: str, *, future: bool, poolclass: type[NullPool], hide_parameters: bool) -> Engine:
        engine = create_engine(url, future=future, poolclass=poolclass, hide_parameters=hide_parameters)
        event.listen(engine, "engine_connect", connections.append)
        return engine

    monkeypatch.setattr(lock_module, "create_engine", observe_engine)
    with migration_lock(_ORACLE_URL, timeout_seconds=5):
        assert len(connections) == 1
        connections[0].commit()
        contender = _spawn(processes, tmp_path / "contender.ready", tmp_path / "release", timeout=0.25)
        _completed(contender, "timeout", code=4)
        assert not (tmp_path / "contender.ready").exists()


def test_oracle_mutex_releases_after_another_process_body_fails(
    processes: list[subprocess.Popen[str]], tmp_path: Path
) -> None:
    ready, release = tmp_path / "holder.ready", tmp_path / "holder.release"
    holder = _spawn(processes, ready, release, mode="exception")
    _wait_for_marker(holder, ready)
    release.touch()
    _completed(holder, "body_failure_released")
    with migration_lock(_ORACLE_URL, timeout_seconds=5):
        pass


def test_oracle_mutex_releases_after_holder_process_is_killed(
    processes: list[subprocess.Popen[str]], tmp_path: Path
) -> None:
    ready = tmp_path / "holder.ready"
    holder = _spawn(processes, ready, tmp_path / "holder.release")
    _wait_for_marker(holder, ready)
    holder.kill()
    assert holder.wait(timeout=10) != 0
    with migration_lock(_ORACLE_URL, timeout_seconds=10):
        pass
