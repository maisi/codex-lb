from __future__ import annotations

from dataclasses import dataclass, field
from types import TracebackType

import pytest
from sqlalchemy import exc as sa_exc
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.elements import TextClause

import app.db.migration_lock as lock_module
from app.db.migration_lock import OracleMigrationLockError, migration_lock

_URL = "oracle+oracledb://user:secret-marker@localhost/service"


@dataclass
class _Result:
    out_parameters: dict[str, int]


@dataclass
class _Connection:
    request_codes: list[int] = field(default_factory=lambda: [0])
    release_code: int = 0
    request_error: Exception | None = None
    release_error: Exception | None = None
    statements: list[str] = field(default_factory=list)
    lock_ids: list[int] = field(default_factory=list)
    closed: bool = False

    def __enter__(self) -> _Connection:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self.closed = True

    def execute(self, statement: TextClause, parameters: dict[str, int]) -> _Result:
        sql = str(statement)
        self.statements.append(sql)
        self.lock_ids.append(parameters["lock_id"])
        if "DBMS_LOCK.REQUEST" in sql:
            if self.request_error is not None:
                raise self.request_error
            code = self.request_codes.pop(0) if len(self.request_codes) > 1 else self.request_codes[0]
            return _Result({"result": code})
        assert "DBMS_LOCK.RELEASE" in sql
        if self.release_error is not None:
            raise self.release_error
        return _Result({"result": self.release_code})


@dataclass
class _Engine:
    connection: _Connection = field(default_factory=_Connection)
    disposed: bool = False
    connect_error: Exception | None = None

    def connect(self) -> _Connection:
        if self.connect_error is not None:
            raise self.connect_error
        return self.connection

    def dispose(self) -> None:
        self.disposed = True


@pytest.fixture
def oracle_engine(monkeypatch: pytest.MonkeyPatch) -> _Engine:
    engine = _Engine()

    def create_engine(url: str, *, future: bool, poolclass: type[NullPool], hide_parameters: bool) -> _Engine:
        assert make_url(url).get_backend_name().lower() == "oracle"
        assert future is True
        assert poolclass is NullPool
        assert hide_parameters is True
        return engine

    monkeypatch.setattr(lock_module, "create_oracle_sync_engine", create_engine)
    return engine


@pytest.mark.parametrize("driver", ["oracle", "oracle+oracledb", "oracle+cx_oracle", "Oracle+ORACLEDB"])
def test_oracle_mutex_owns_a_dedicated_session_until_body_finishes(driver: str, oracle_engine: _Engine) -> None:
    with migration_lock(_URL.replace("oracle+oracledb", driver), timeout_seconds=1):
        assert not oracle_engine.connection.closed
        assert not oracle_engine.disposed
        assert len(oracle_engine.connection.statements) == 1

    assert oracle_engine.connection.closed
    assert oracle_engine.disposed
    request, release = oracle_engine.connection.statements
    assert "release_on_commit => FALSE" in request
    assert "timeout => 0" in request
    assert "DBMS_LOCK.RELEASE" in release
    first_id, second_id = oracle_engine.connection.lock_ids
    assert first_id == second_id
    assert 0 <= first_id < (1 << 30)


def test_oracle_mutex_polls_only_for_another_owner(oracle_engine: _Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    oracle_engine.connection.request_codes = [1, 0]
    sleeps: list[float] = []
    monkeypatch.setattr(lock_module.time, "sleep", sleeps.append)

    with migration_lock(_URL, timeout_seconds=5):
        pass

    assert len(sleeps) == 1
    assert len(oracle_engine.connection.statements) == 3
    assert oracle_engine.connection.closed


def test_oracle_mutex_timeout_closes_session_without_running_body(
    oracle_engine: _Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    oracle_engine.connection.request_codes = [1]
    times = iter([0.0, 1.0])
    monkeypatch.setattr(lock_module.time, "monotonic", lambda: next(times))

    with pytest.raises(TimeoutError, match="Oracle DBMS_LOCK migration lock"):
        with migration_lock(_URL, timeout_seconds=0.1):
            pytest.fail("An unowned mutex must not enter the migration body")

    assert len(oracle_engine.connection.statements) == 1
    assert oracle_engine.connection.closed
    assert oracle_engine.disposed


@pytest.mark.parametrize("code", [2, 3, 4, 5])
def test_oracle_mutex_request_failures_do_not_enter_body(code: int, oracle_engine: _Engine) -> None:
    oracle_engine.connection.request_codes = [code]

    with pytest.raises(OracleMigrationLockError, match=f"REQUEST failed with result code {code}"):
        with migration_lock(_URL, timeout_seconds=1):
            pytest.fail("A failed mutex must not enter the migration body")

    assert len(oracle_engine.connection.statements) == 1
    assert oracle_engine.connection.closed
    assert oracle_engine.disposed


@pytest.mark.parametrize(
    "oracle_error",
    ["ORA-06550: PLS-00201: identifier 'DBMS_LOCK' must be declared", "ORA-01031: insufficient privileges"],
)
def test_oracle_mutex_permission_errors_are_actionable(oracle_error: str, oracle_engine: _Engine) -> None:
    oracle_engine.connection.request_error = sa_exc.DatabaseError(None, None, Exception(oracle_error))

    with pytest.raises(OracleMigrationLockError, match="requires EXECUTE on SYS.DBMS_LOCK") as exc_info:
        with migration_lock(_URL, timeout_seconds=1):
            pytest.fail("Missing DBMS_LOCK permission must never fall back to unlocked migration")

    assert "secret-marker" not in str(exc_info.value)
    assert oracle_engine.connection.closed
    assert oracle_engine.disposed


def test_oracle_mutex_preserves_unrelated_driver_failure(oracle_engine: _Engine) -> None:
    failure = sa_exc.DatabaseError(None, None, Exception("ORA-03113: end-of-file on communication channel"))
    oracle_engine.connection.request_error = failure

    with pytest.raises(sa_exc.DatabaseError) as exc_info:
        with migration_lock(_URL, timeout_seconds=1):
            pytest.fail("A disconnected mutex must not enter the migration body")

    assert exc_info.value is failure
    assert oracle_engine.connection.closed
    assert oracle_engine.disposed


@pytest.mark.parametrize("release_failure", ["return-code", "exception"])
def test_oracle_mutex_release_failure_preserves_original_body_error(
    release_failure: str, oracle_engine: _Engine, caplog: pytest.LogCaptureFixture
) -> None:
    if release_failure == "return-code":
        oracle_engine.connection.release_code = 4
    else:
        oracle_engine.connection.release_error = RuntimeError("release failed")
    failure = ValueError("migration failed")

    with pytest.raises(ValueError) as exc_info:
        with migration_lock(_URL, timeout_seconds=1):
            raise failure

    assert exc_info.value is failure
    assert oracle_engine.connection.closed
    assert oracle_engine.disposed
    assert "closing its dedicated session" in caplog.text


def test_oracle_mutex_release_failure_is_reported_on_normal_exit(oracle_engine: _Engine) -> None:
    oracle_engine.connection.release_code = 4

    with pytest.raises(OracleMigrationLockError, match="RELEASE failed with result code 4"):
        with migration_lock(_URL, timeout_seconds=1):
            pass

    assert oracle_engine.connection.closed
    assert oracle_engine.disposed


def test_oracle_mutex_disposes_engine_if_connect_fails(oracle_engine: _Engine) -> None:
    oracle_engine.connect_error = RuntimeError("connection failed")

    with pytest.raises(RuntimeError, match="connection failed"):
        with migration_lock(_URL, timeout_seconds=1):
            pytest.fail("A disconnected mutex must not enter the migration body")

    assert oracle_engine.disposed


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_oracle_mutex_rejects_invalid_timeout_before_engine_creation(
    timeout: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_engine_creation(*args: object, **kwargs: object) -> None:
        pytest.fail("Invalid mutex timeout must fail before opening a connection")

    monkeypatch.setattr(lock_module, "create_engine", unexpected_engine_creation)

    with pytest.raises(ValueError, match="finite and greater than 0"):
        with migration_lock(_URL, timeout_seconds=timeout):
            pytest.fail("Invalid mutex timeout must not enter the migration body")
