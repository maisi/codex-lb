from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts/migrate-sqlite-to-oracle-docker.sh"
_DOCKER = r"""
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with Path(os.environ['DOCKER_LOG']).open('a') as log:
    log.write(json.dumps(args) + '\n')
state = Path(os.environ['DOCKER_STATE'])
stage = args[0]
if args[:2] == ['container', 'inspect']:
    if '.State.Running' in args[3]:
        print(state.read_text())
    else:
        print(os.environ.get('DOCKER_MOUNTS', '/var/lib/codex-lb'))
    sys.exit(0)
if args[0] == 'run':
    if '-c' in args:
        stage = 'probe'
    elif 'oracle-check' in args:
        stage = 'oracle-check'
    elif 'migrate-to-oracle' in args:
        stage = 'dry-run' if '--dry-run' in args else 'transfer'
    elif 'check' in args:
        stage = 'check'
if stage == 'stop':
    state.write_text('false')
if stage == 'cp':
    destination = Path(args[-1])
    for name in ['store.db', 'store.db-wal', 'store.db-shm', 'encryption.key']:
        (destination / name).write_text('original-' + name)
    (destination / 'conversation-archive').mkdir()
    (destination / 'conversation-archive' / 'log.json').write_text('{}')
    if os.environ.get('DOCKER_RESTART_ON_COPY'):
        state.write_text('true')
if os.environ.get('DOCKER_FAIL_STAGE') == stage:
    print('simulated docker failure at ' + stage, file=sys.stderr)
    sys.exit(23)
"""


@dataclass
class DockerHarness:
    environment: dict[str, str]
    env_file: Path
    backup: Path
    log: Path
    state: Path

    def run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(_SCRIPT), "--env-file", str(self.env_file), "--backup-dir", str(self.backup), *arguments],
            env=self.environment,
            text=True,
            capture_output=True,
            timeout=15,
        )

    def calls(self) -> list[list[str]]:
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []


@pytest.fixture
def docker(tmp_path: Path) -> DockerHarness:
    binary = tmp_path / "bin"
    binary.mkdir()
    executable = binary / "docker"
    executable.write_text(f"#!{sys.executable}\n" + _DOCKER)
    executable.chmod(0o700)
    log = tmp_path / "docker.jsonl"
    state = tmp_path / "state"
    state.write_text("true")
    env_file = tmp_path / "oracle credentials.env"
    env_file.write_text("CODEX_LB_DATABASE_URL=oracle+oracledb://user:never-print-secret@host/\n")
    environment = {
        **os.environ,
        "PATH": str(binary) + os.pathsep + os.environ["PATH"],
        "DOCKER_LOG": str(log),
        "DOCKER_STATE": str(state),
    }
    return DockerHarness(environment, env_file, tmp_path / "private backup", log, state)


def _stage(call: list[str]) -> str:
    if call[0] != "run":
        return call[0]
    if "-c" in call:
        return "probe"
    if "migrate-to-oracle" in call:
        return "dry-run" if "--dry-run" in call else "transfer"
    return next(word for word in ("oracle-check", "check") if word in call)


def test_apply_stops_backs_up_and_transfers_without_starting_application(docker: DockerHarness) -> None:
    result = docker.run("--apply", "--build")
    assert result.returncode == 0, result.stderr
    stages = [_stage(call) for call in docker.calls()]
    expected = ["build", "probe", "oracle-check", "stop", "cp", "dry-run", "transfer", "check"]
    assert [stage for stage in stages if stage in expected] == expected
    assert docker.state.read_text() == "false"
    assert stat.S_IMODE(docker.backup.stat().st_mode) == 0o700
    for name in ["store.db", "store.db-wal", "store.db-shm", "encryption.key", "conversation-archive/log.json"]:
        assert (docker.backup / name).is_file()
    assert all(call[0] != "start" and "-d" not in call for call in docker.calls())
    assert "Example application command (not executed)" in result.stdout
    assert "never-print-secret" not in result.stdout + result.stderr


@pytest.mark.parametrize("explicit", [False, True])
def test_dry_run_requires_stopped_source_and_never_stops_it(docker: DockerHarness, explicit: bool) -> None:
    result = docker.run(*(["--dry-run"] if explicit else []))
    assert result.returncode != 0
    assert "stopped source" in result.stderr
    assert docker.state.read_text() == "true"
    assert not docker.backup.exists()
    assert not any(call[0] in {"stop", "cp", "run"} for call in docker.calls())


def test_stopped_source_dry_run_has_no_backup_or_transfer(docker: DockerHarness) -> None:
    docker.state.write_text("false")
    result = docker.run()
    assert result.returncode == 0, result.stderr
    assert [_stage(call) for call in docker.calls() if call[0] == "run"] == ["probe", "oracle-check", "dry-run"]
    assert not docker.backup.exists()


@pytest.mark.parametrize("failure", ["probe", "oracle-check", "cp", "dry-run", "transfer", "check"])
def test_failure_stops_following_stages_and_never_restarts(docker: DockerHarness, failure: str) -> None:
    docker.environment["DOCKER_FAIL_STAGE"] = failure
    result = docker.run("--apply")
    assert result.returncode != 0
    stages = [_stage(call) for call in docker.calls()]
    assert stages[-1] == failure
    assert "start" not in stages and stages.count("transfer") <= 1
    if failure in {"probe", "oracle-check"}:
        assert docker.state.read_text() == "true" and not docker.backup.exists()
    else:
        assert docker.state.read_text() == "false" and docker.backup.exists()
        assert "will not be restarted automatically" in result.stderr


@pytest.mark.parametrize("mounts", ["/other", "/app\n/var/lib/codex-lb", "/app/app\n/var/lib/codex-lb", "/"])
def test_unsafe_source_mounts_are_rejected_before_stop(docker: DockerHarness, mounts: str) -> None:
    docker.environment["DOCKER_MOUNTS"] = mounts
    result = docker.run("--apply")
    assert result.returncode != 0
    assert not any(call[0] == "stop" for call in docker.calls())
    assert not docker.backup.exists()


def test_existing_backup_is_preserved_before_any_docker_calls(docker: DockerHarness) -> None:
    docker.backup.mkdir()
    marker = docker.backup / "original"
    marker.write_text("keep")
    result = docker.run("--apply")
    assert result.returncode != 0
    assert marker.read_text() == "keep"
    assert docker.calls() == []


def test_restart_during_backup_prevents_transfer(docker: DockerHarness) -> None:
    docker.environment["DOCKER_RESTART_ON_COPY"] = "yes"
    result = docker.run("--apply")
    assert result.returncode != 0
    assert "restarted during backup" in result.stderr
    assert not any("migrate-to-oracle" in call for call in docker.calls())


def test_helper_options_preserve_exact_arguments_and_never_source_environment(docker: DockerHarness) -> None:
    marker = docker.env_file.parent / "executed"
    docker.env_file.write_text(f"CODEX_LB_DATABASE_URL=never-print-secret\nBAD=$(touch {marker})\n")
    wallet = f"type=bind,src={docker.env_file.parent}/wallet $(touch injected),dst=/wallet,readonly"
    key_mount = "type=bind,src=/private/keys,dst=/custom keys,readonly"
    key = "/custom keys/encryption.key"
    result = docker.run(
        "--apply", "--network", "private-net", "--mount", wallet, "--mount", key_mount, "--source-key-file", key
    )
    assert result.returncode == 0, result.stderr
    for call in (call for call in docker.calls() if call[0] == "run"):
        assert call[call.index("--env-file") + 1] == str(docker.env_file)
        assert call[call.index("--network") + 1] == "private-net"
        assert [call[index + 1] for index, word in enumerate(call) if word == "--mount"] == [wallet, key_mount]
        assert call[call.index("--entrypoint") + 1] == "python"
        if "migrate-to-oracle" in call:
            assert call[call.index("--source-key-file") + 1] == key
    assert not marker.exists()
    assert "never-print-secret" not in result.stdout + result.stderr


@pytest.mark.parametrize("arguments", [("--apply", "--dry-run"), ("--network",), ("--unknown",)])
def test_invalid_options_fail_without_docker(docker: DockerHarness, arguments: tuple[str, ...]) -> None:
    assert docker.run(*arguments).returncode != 0
    assert docker.calls() == []


def test_custom_data_mount_and_database_are_backed_up_together(docker: DockerHarness) -> None:
    docker.environment["DOCKER_MOUNTS"] = "/srv"
    result = docker.run("--apply", "--data-dir", "/srv/codex data", "--source-sqlite", "/srv/codex data/custom.db")
    assert result.returncode == 0, result.stderr
    copy = next(call for call in docker.calls() if call[0] == "cp")
    assert copy[1] == "codex-lb:/srv/codex data/."
    for call in docker.calls():
        if "migrate-to-oracle" in call:
            assert call[call.index("--source-sqlite") + 1] == "/srv/codex data/custom.db"


def test_apply_also_accepts_an_already_stopped_source(docker: DockerHarness) -> None:
    docker.state.write_text("false")
    result = docker.run("--apply")
    assert result.returncode == 0, result.stderr
    assert docker.state.read_text() == "false"
    assert (docker.backup / "encryption.key").is_file()


@pytest.mark.parametrize("database", ["/outside/store.db", "/var/lib/codex-lb/../store.db"])
def test_database_outside_backup_is_refused_before_docker(docker: DockerHarness, database: str) -> None:
    result = docker.run("--apply", "--source-sqlite", database)
    assert result.returncode != 0
    assert docker.calls() == []
