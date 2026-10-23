from __future__ import annotations

import asyncio
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from sqlalchemy.engine import URL, make_url

if TYPE_CHECKING:
    import oracledb

_CHECK_SQL = "SELECT 1 FROM DUAL"
_MAX_TIMEOUT_SECONDS = 300.0
_URL_OPTIONS = frozenset(
    {"service_name", "protocol", "config_dir", "wallet_location", "wallet_password", "ssl_server_cert_dn"}
)


class OraclePreflightError(ValueError):
    """A preparation error whose message is safe to print to an operator."""


@dataclass(frozen=True)
class OracleSessionBudget:
    pool_size: int
    max_overflow: int
    replicas: int = 1
    extra_replicas: int = 0
    session_limit: int = 30

    def __post_init__(self) -> None:
        for name, value in (
            ("pool_size", self.pool_size),
            ("replicas", self.replicas),
            ("session_limit", self.session_limit),
        ):
            if type(value) is not int or value <= 0:
                raise OraclePreflightError(f"{name} must be a positive integer")
        for name, value in (("max_overflow", self.max_overflow), ("extra_replicas", self.extra_replicas)):
            if type(value) is not int or value < 0:
                raise OraclePreflightError(f"{name} must be a non-negative integer")

    @property
    def sessions_per_replica(self) -> int:
        # Request and background engines have independent pools.
        return 2 * (self.pool_size + self.max_overflow)

    @property
    def steady_sessions(self) -> int:
        return self.sessions_per_replica * self.replicas

    @property
    def overlap_sessions(self) -> int:
        return self.sessions_per_replica * (self.replicas + self.extra_replicas)

    @property
    def remaining_sessions(self) -> int:
        return self.session_limit - self.overlap_sessions

    def require_capacity(self) -> None:
        if self.remaining_sessions <= 0:
            raise OraclePreflightError(
                "Connection budget leaves no operational reserve: "
                f"2 pools * ({self.pool_size} pool_size + {self.max_overflow} max_overflow) * "
                f"({self.replicas} replicas + {self.extra_replicas} extra_replicas) = "
                f"{self.overlap_sessions} sessions, session_limit={self.session_limit}. "
                "Deliberately lower pool size/overflow or replica overlap; the existing application defaults "
                "are not suitable for Always Free."
            )


def _oracle_url(database_url: str) -> URL:
    try:
        url = make_url(database_url)
        port = url.port
    except Exception:
        raise OraclePreflightError(
            "Invalid Oracle URL; use oracle+oracledb://user:password@host/?service_name=..."
        ) from None
    if url.drivername != "oracle+oracledb":
        raise OraclePreflightError("Oracle preparation requires the native oracle+oracledb:// URL.")
    if not url.host or not url.username or not url.password:
        raise OraclePreflightError("Oracle URL must include a username, password and host or TNS alias.")
    if port is not None and not 1 <= port <= 65535:
        raise OraclePreflightError("Oracle URL port must be between 1 and 65535.")
    if url.database and "service_name" in url.query:
        raise OraclePreflightError("Use either an Oracle SID in the URL path or service_name, not both.")
    if port is not None and not url.database and "service_name" not in url.query:
        raise OraclePreflightError("An Oracle host and port require service_name or a SID in the URL path.")
    if any(key not in _URL_OPTIONS or not isinstance(value, str) for key, value in url.query.items()):
        raise OraclePreflightError(
            "Unsupported or repeated Oracle URL option. Supported options: " + ", ".join(sorted(_URL_OPTIONS)) + "."
        )
    if url.query.get("protocol", "tcp") not in {"tcp", "tcps"}:
        raise OraclePreflightError("Oracle URL protocol must be tcp or tcps.")
    return url


def _validate_timeout(timeout_seconds: float) -> None:
    if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= _MAX_TIMEOUT_SECONDS:
        raise OraclePreflightError("timeout_seconds must be finite, greater than zero and at most 300 seconds.")


def run_oracle_preflight(
    database_url: str,
    budget: OracleSessionBudget,
    *,
    budget_only: bool = False,
    timeout_seconds: float = 10.0,
) -> None:
    _validate_timeout(timeout_seconds)
    print("oracle_runtime_support=unverified; application startup and schema mutation remain unsupported")
    print(f"pool_count_per_replica=2 pool_size={budget.pool_size} max_overflow={budget.max_overflow}")
    print(f"replicas={budget.replicas} extra_replicas={budget.extra_replicas} session_limit={budget.session_limit}")
    print(f"steady_sessions={budget.steady_sessions}")
    print(f"overlap_sessions={budget.overlap_sessions}")
    print(f"remaining_sessions={budget.remaining_sessions}")
    budget.require_capacity()
    if budget_only:
        print("oracle_connection=not_checked (budget only)")
    else:
        version = check_oracle_connection(database_url, timeout_seconds=timeout_seconds)
        print("oracle_sync_thin_connection=ok")
        print("oracle_async_thin_connection=ok")
        print(f"oracle_server_version={version}")
    print("session_budget=ok; capacity estimate only, not a throughput or HA guarantee")


def check_oracle_connection(database_url: str, *, timeout_seconds: float = 10.0) -> str:
    """Check both native Thin paths within one hard deadline; never forward driver output."""
    _oracle_url(database_url)
    _validate_timeout(timeout_seconds)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.db.oracle_preflight"],
            input=json.dumps({"database_url": database_url, "timeout_seconds": timeout_seconds}),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise OraclePreflightError(
            "Oracle connectivity check timed out; its worker was stopped and connections released. "
            "Check DNS, network access, service name and wallet configuration, or increase --timeout-seconds."
        ) from None
    except OSError:
        raise OraclePreflightError(
            "Could not start Oracle connectivity worker; check the Python installation."
        ) from None
    # Only explicitly structured worker results may reach the terminal. Driver
    # tracebacks can contain passwords, wallet options and full connection URLs.
    try:
        payload = json.loads(result.stdout)
        status, detail = payload["status"], payload["detail"]
        if not isinstance(detail, str) or status not in {"ok", "error"}:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise OraclePreflightError(
            "Oracle connectivity worker failed; check the driver installation and retry."
        ) from None
    if result.returncode != 0 or status != "ok":
        # The child only emits messages constructed by _safe_error below.
        raise OraclePreflightError(detail)
    if re.fullmatch(r"\d+(?:\.\d+){0,5}", detail) is None:
        raise OraclePreflightError("Oracle returned an unexpected server version; connectivity could not be verified.")
    return detail


def _url_option(url: URL, key: str) -> str | None:
    return cast(str | None, url.query.get(key))


def _connection_params(url: URL, timeout_seconds: float) -> oracledb.ConnectParams:
    import oracledb

    # URL options are allowlisted to exclude password changes, privileged modes
    # and callback execution. Certificate hostname verification stays enabled.
    params = oracledb.ConnectParams(
        user=url.username,
        password=url.password,
        port=url.port or 1521,
        config_dir=_url_option(url, "config_dir"),
        tcp_connect_timeout=timeout_seconds,
        retry_count=0,
        ssl_server_dn_match=True,
    )
    if url.database or "service_name" in url.query:
        params.set(host=url.host, sid=url.database, service_name=_url_option(url, "service_name"))
    else:
        # Resolve a TNS alias with its wallet/configuration before imposing our
        # retry/connect limits; descriptor values must not override the limits.
        params.parse_connect_string(cast(str, url.host))
    params.set(
        protocol=_url_option(url, "protocol"),
        wallet_location=_url_option(url, "wallet_location"),
        wallet_password=_url_option(url, "wallet_password"),
        ssl_server_cert_dn=_url_option(url, "ssl_server_cert_dn"),
        tcp_connect_timeout=timeout_seconds,
        retry_count=0,
        ssl_server_dn_match=True,
    )
    return params


async def _check_async(params: oracledb.ConnectParams, timeout_seconds: float) -> str:
    import oracledb

    async with asyncio.timeout(timeout_seconds):
        async with oracledb.connect_async(params=params) as connection:
            connection.call_timeout = max(1, math.ceil(timeout_seconds * 1000))
            with connection.cursor() as cursor:
                await cursor.execute(_CHECK_SQL)
                if await cursor.fetchone() != (1,):
                    raise OraclePreflightError("Oracle asynchronous read-only query returned an unexpected result.")
            return connection.version


def _check_connections(database_url: str, timeout_seconds: float) -> str:
    import oracledb

    if not oracledb.is_thin_mode():
        raise OraclePreflightError(
            "Oracle preparation requires Thin mode; start a fresh process without Oracle Client initialization."
        )
    params = _connection_params(_oracle_url(database_url), timeout_seconds)
    with oracledb.connect(params=params) as connection:
        connection.call_timeout = max(1, math.ceil(timeout_seconds * 1000))
        with connection.cursor() as cursor:
            cursor.execute(_CHECK_SQL)
            if cursor.fetchone() != (1,):
                raise OraclePreflightError("Oracle synchronous read-only query returned an unexpected result.")
        version = connection.version
    async_version = asyncio.run(_check_async(params, timeout_seconds))
    if async_version != version:
        raise OraclePreflightError(
            "Oracle sync/async connections returned different server versions; verify the target service."
        )
    return version


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, OraclePreflightError):
        return str(exc)
    if isinstance(exc, ModuleNotFoundError):
        return "Oracle Thin driver is unavailable; install the optional dependency with uv sync --extra oracle."
    # python-oracledb exposes a structured full_code on its error detail. Never
    # search arbitrary exception text: even a code-shaped substring can belong
    # to a connection URL or wallet secret.
    full_code = getattr(exc.args[0], "full_code", None) if exc.args else None
    code = (
        f" ({full_code})" if isinstance(full_code, str) and re.fullmatch(r"(?:ORA|DPY|DPI)-\d{4,5}", full_code) else ""
    )
    return (
        f"Oracle connectivity failed{code}; check credentials, network access, service name and Thin wallet "
        "configuration. Driver details were withheld to protect credentials."
    )


def _worker_main() -> None:
    try:
        payload = json.load(sys.stdin)
        detail = _check_connections(payload["database_url"], payload["timeout_seconds"])
    except Exception as exc:
        print(json.dumps({"status": "error", "detail": _safe_error(exc)}))
        raise SystemExit(1) from None
    print(json.dumps({"status": "ok", "detail": detail}))


if __name__ == "__main__":
    _worker_main()
