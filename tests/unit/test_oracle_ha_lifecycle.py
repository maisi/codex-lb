"""The opt-in HA harness must reap children even when its own setup fails."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.integration.oracle_ha_support import Cluster


def test_partial_startup_reaps_previously_started_children(tmp_path: Path) -> None:
    cluster = Cluster(tmp_path / "ha", "oracle+oracledb://unused:unused@localhost/")
    try:
        running = cluster.spawn(
            "started", [sys.executable, "-c", "import time; time.sleep(120)"], cluster.environment(), port=0
        )
        failing = cluster.spawn("failed", [sys.executable, "-c", "raise SystemExit(7)"], cluster.environment(), port=0)
        with pytest.raises(RuntimeError, match="exited during startup"):
            cluster.wait_ready(failing, "/health/ready", timeout=5)
    finally:
        cluster.close()
    assert running.process.poll() is not None
    assert failing.process.returncode == 7
    assert all(child.output.closed for child in cluster.children)


def test_damaged_observation_log_still_reaps_children(tmp_path: Path) -> None:
    cluster = Cluster(tmp_path / "ha", "oracle+oracledb://unused:unused@localhost/")
    running = cluster.spawn(
        "started", [sys.executable, "-c", "import time; time.sleep(120)"], cluster.environment(), port=0
    )
    (cluster.directory / "events.jsonl").write_text('{"incomplete":')
    with pytest.raises(ExceptionGroup, match="HA child cleanup failed"):
        cluster.close()
    assert running.process.poll() is not None
    assert running.output.closed
