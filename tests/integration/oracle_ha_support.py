"""Owned real-process Oracle/HAProxy acceptance support."""

from __future__ import annotations

import json
import os
import random
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO, TypeVar
from urllib.parse import quote, quote_plus

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import inspect
from sqlalchemy.engine import Engine, make_url

from app.core.runtime_logging import redact_rendered_log_text

ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("oracle_ha_worker.py")
T = TypeVar("T")


def require_empty_schema(engine: Engine) -> None:
    with engine.connect() as connection:
        inspector = inspect(connection)
        if inspector.get_table_names() or inspector.get_view_names() or inspector.get_sequence_names():
            raise RuntimeError("Oracle HA acceptance requires an empty owned schema; existing objects are preserved.")


def free_port() -> int:
    # Ports are chosen before their processes start (HAProxy needs ha-c up
    # front). Stay below the kernel's ephemeral range so outbound Oracle and
    # health-check sockets cannot claim a reserved port in the meantime.
    low = 32768
    try:
        low = int(Path("/proc/sys/net/ipv4/ip_local_port_range").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        pass
    candidates = list(range(10000, max(low, 10200)))
    random.shuffle(candidates)
    for port in candidates[:200]:
        with socket.socket() as listener:
            try:
                listener.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No free non-ephemeral port for the Oracle HA acceptance processes.")


def eventually(label: str, check: Callable[[], T], *, timeout: float = 30) -> T:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except (httpx.HTTPError, AssertionError) as exc:
            last_error = exc
        time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for {label}; last_error={type(last_error).__name__}: {last_error}")


@dataclass
class Child:
    name: str
    process: subprocess.Popen[bytes]
    log: Path
    output: TextIO
    port: int

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def kill(self) -> None:
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(timeout=15)

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.kill()
                raise AssertionError(f"Owned {self.name} did not stop within its shutdown deadline.") from None


@dataclass
class Cluster:
    directory: Path
    database_url: str = field(repr=False)
    children: list[Child] = field(default_factory=list)
    secrets: list[str] = field(default_factory=list, repr=False)
    ports: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.directory.mkdir(mode=0o700, exist_ok=True)
        (self.directory / "encryption.key").write_bytes(Fernet.generate_key())
        (self.directory / "encryption.key").chmod(0o600)
        self.ports = {name: free_port() for name in ("upstream", "gateway", "ha-a", "ha-b", "ha-c")}
        assert len(set(self.ports.values())) == len(self.ports)
        url = make_url(self.database_url)
        self.secrets.extend(
            value
            for value in (self.database_url, url.password, url.query.get("wallet_password"))
            if isinstance(value, str) and value
        )

    def environment(self) -> dict[str, str]:
        allowed = {"PATH", "HOME", "LANG", "LC_ALL", "TZ", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR", "LD_LIBRARY_PATH"}
        return {key: value for key, value in os.environ.items() if key in allowed}

    def spawn(self, name: str, arguments: list[str], environment: dict[str, str], *, port: int) -> Child:
        path = self.directory / f"{name}-{len(self.children)}.log"
        output = path.open("w")
        try:
            process = subprocess.Popen(
                arguments, cwd=ROOT, env=environment, stdout=output, stderr=subprocess.STDOUT, start_new_session=True
            )
        except BaseException:
            output.close()
            raise
        child = Child(name, process, path, output, port)
        self.children.append(child)
        return child

    def start_upstream(self) -> Child:
        env = self.environment()
        env["PYTHONPATH"] = str(ROOT)
        child = self.spawn(
            "upstream",
            [
                sys.executable,
                str(WORKER),
                "upstream",
                "--port",
                str(self.ports["upstream"]),
                "--control",
                str(self.directory),
            ],
            env,
            port=self.ports["upstream"],
        )
        self.wait_ready(child, "/health")
        return child

    def start_node(self, name: str) -> Child:
        upstream = f"http://127.0.0.1:{self.ports['upstream']}"
        env = self.environment()
        env.update(
            {
                "PYTHONPATH": str(ROOT),
                "CODEX_LB_DATABASE_URL": self.database_url,
                "CODEX_LB_DATA_DIR": str(self.directory / name),
                "CODEX_LB_ENCRYPTION_KEY_FILE": str(self.directory / "encryption.key"),
                "CODEX_LB_ENV_FILE": str(self.directory / "missing.env"),
                "CODEX_LB_HTTP_RESPONSES_SESSION_BRIDGE_INSTANCE_ID": name,
                "CODEX_LB_HTTP_RESPONSES_SESSION_BRIDGE_ADVERTISE_BASE_URL": f"http://{name}.localhost:{self.ports[name]}",
                "CODEX_LB_UPSTREAM_BASE_URL": upstream + "/backend-api",
                "CODEX_LB_UPSTREAM_ROUTE_CACHE_TTL_SECONDS": "0",
                "CODEX_LB_LEADER_ELECTION_TTL_SECONDS": "15",
                "CODEX_LB_METRICS_ENABLED": "false",
                "CODEX_LB_TELEMETRY_ENABLED": "false",
                "CODEX_LB_DASHBOARD_BOOTSTRAP_TOKEN": "ha-test-bootstrap-only",
                "CODEX_LB_SHUTDOWN_DRAIN_TIMEOUT_SECONDS": "10",
            }
        )
        child = self.spawn(
            name,
            [
                sys.executable,
                str(WORKER),
                "node",
                "--port",
                str(self.ports[name]),
                "--control",
                str(self.directory),
                "--upstream",
                upstream,
            ],
            env,
            port=self.ports[name],
        )
        self.wait_ready(child, "/health/ready", timeout=150)
        return child

    def wait_ready(self, child: Child, route: str, *, timeout: float = 30) -> None:
        with httpx.Client(trust_env=False, timeout=3) as client:

            def check() -> bool:
                if child.process.poll() is not None:
                    raise RuntimeError(f"Owned {child.name} exited during startup (exit={child.process.returncode}).")
                return client.get(child.url + route).status_code == 200

            eventually(f"{child.name} readiness", check, timeout=timeout)

    def start_gateway(self) -> Child:
        binary = os.environ.get("CODEX_LB_TEST_HAPROXY_BIN") or shutil.which("haproxy")
        if not binary:
            raise RuntimeError(
                "Oracle HA acceptance requires HAProxy; install haproxy or set CODEX_LB_TEST_HAPROXY_BIN."
            )
        config = self.directory / "haproxy.cfg"
        # Exercise the operator example itself, changing only addresses and
        # adding observation plus the rolling replacement's third backend.
        template = (ROOT / "deploy/oracle-ha/haproxy.cfg").read_text()
        template = template.replace("bind 127.0.0.1:2455", f"bind 127.0.0.1:{self.ports['gateway']}")
        for name, address in (("ha-a", "10.20.0.11:2455"), ("ha-b", "10.20.0.12:2455")):
            template = template.replace(address, f"127.0.0.1:{self.ports[name]}")
        config.write_text(
            template
            + "    http-response set-header X-HA-Test-Backend %[srv_name]\n"
            + f"    server ha-c 127.0.0.1:{self.ports['ha-c']} cookie ha-c check inter 1s fall 2 rise 2\n"
        )
        result = subprocess.run(
            [binary, "-c", "-f", str(config)], env=self.environment(), capture_output=True, timeout=10
        )
        if result.returncode:
            raise AssertionError(
                "Generated HAProxy configuration was rejected: " + result.stderr.decode(errors="replace")
            )
        child = self.spawn(
            "gateway", [binary, "-db", "-f", str(config)], self.environment(), port=self.ports["gateway"]
        )
        self.wait_ready(child, "/health/ready")
        return child

    def events(self, kind: str) -> list[dict[str, Any]]:
        path = self.directory / "events.jsonl"
        if not path.exists():
            return []
        return [event for line in path.read_text().splitlines() if (event := json.loads(line))["kind"] == kind]

    def release(self, name: str) -> None:
        (self.directory / f"release-{name}").touch()

    def close(self) -> None:
        errors: list[Exception] = []
        try:
            for event in self.events("upstream_start"):
                if event["request"].startswith("hold-"):
                    self.release(event["request"])
        except Exception as exc:
            # A damaged observation log must never orphan real processes.
            errors.append(exc)
        for child in reversed(self.children):
            try:
                child.stop()
            except Exception as exc:
                errors.append(exc)
            finally:
                child.output.close()
        if errors:
            raise ExceptionGroup("HA child cleanup failed", errors)

    def logs(self) -> str:
        output = "\n".join(
            f"{child.name}:\n{child.log.read_text(errors='replace')[-10000:]}" for child in self.children
        )
        return self.sanitize(output)

    def sanitize(self, output: str) -> str:
        for secret in self.secrets:
            for variant in (secret, quote(secret, safe=""), quote_plus(secret)):
                output = output.replace(variant, "[REDACTED]")
        return redact_rendered_log_text(output)
