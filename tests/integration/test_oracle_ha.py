"""Opt-in real-process Oracle failover through HAProxy and a wire upstream."""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import Column, Integer, MetaData, Table, inspect, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.balancer.rendezvous_hash import select_node
from app.core.utils.time import to_utc_naive, utcnow
from app.db.models import (
    Account,
    ApiKeyLimit,
    ApiKeyUsageReservation,
    ApiKeyUsageReservationItem,
    Base,
    HttpBridgeOperationRecord,
    HttpBridgeSessionRecord,
    RequestLog,
)
from app.db.oracle_connection import create_oracle_async_engine, create_oracle_sync_engine
from app.modules.proxy.durable_bridge_repository import DurableBridgeRepository
from tests.integration.oracle_ha_support import Child, Cluster, eventually, require_empty_schema
from tests.integration.oracle_ha_worker import identity_token

_URL = os.environ.get("CODEX_LB_TEST_ORACLE_HA_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _URL, reason="Set an isolated CODEX_LB_TEST_ORACLE_HA_URL."),
]


@pytest.fixture
def schema_engine() -> Iterator[Engine]:
    pytest.importorskip("oracledb")
    engine = create_oracle_sync_engine(_URL, poolclass=NullPool)
    try:
        require_empty_schema(engine)
        yield engine
    finally:
        engine.dispose()


def test_oracle_ha_preserves_nonempty_target(schema_engine: Engine) -> None:
    probe = Table("oracle_ha_preservation_probe", MetaData(), Column("value", Integer))
    try:
        with schema_engine.begin() as connection:
            probe.create(connection)
            connection.execute(probe.insert().values(value=7))
        with pytest.raises(RuntimeError, match="existing objects are preserved"):
            require_empty_schema(schema_engine)
        with schema_engine.connect() as connection:
            assert connection.scalar(select(probe.c.value)) == 7
    finally:
        with schema_engine.begin() as connection:
            probe.drop(connection, checkfirst=True)


@pytest.fixture
def cluster(tmp_path: Path, schema_engine: Engine) -> Iterator[Cluster]:
    harness = Cluster(tmp_path / "ha", _URL)
    try:
        yield harness
    finally:
        try:
            harness.close()
        finally:
            # The empty-schema check succeeded before any child was spawned.
            # Drop only application objects installed by our owned children.
            with schema_engine.begin() as connection:
                Base.metadata.drop_all(connection)
                if inspect(connection).has_table("alembic_version"):
                    connection.exec_driver_sql("DROP TABLE alembic_version PURGE")


def _json(response: httpx.Response) -> Any:
    assert response.status_code == 200, f"HTTP {response.status_code}: {response.text}"
    return response.json()


def _payload(name: str) -> dict[str, Any]:
    return {"model": "gpt-5.1", "instructions": name, "input": [], "stream": True}


def _complete(url: str, key: str, name: str) -> httpx.Response:
    with httpx.Client(trust_env=False, timeout=90) as client:
        response = client.post(
            url + "/backend-api/codex/responses", headers={"Authorization": f"Bearer {key}"}, json=_payload(name)
        )
    assert response.status_code == 200, f"HTTP {response.status_code}: {response.text}"
    assert '"response.completed"' in response.text, response.text
    return response


def _bridge_complete(url: str, key: str, name: str, *, session_key: str, previous: str | None = None) -> httpx.Response:
    payload = _payload(name)
    if previous is not None:
        payload["previous_response_id"] = f"resp_{previous}"
    with httpx.Client(trust_env=False, timeout=90) as client:
        response = client.post(
            url + "/v1/responses",
            headers={"Authorization": f"Bearer {key}", "x-codex-session-id": session_key},
            json=payload,
        )
    assert response.status_code == 200, f"HTTP {response.status_code}: {response.text}"
    assert '"response.completed"' in response.text, response.text
    return response


def _bridge_record(engine: Engine, session_key: str) -> HttpBridgeSessionRecord:
    with Session(engine, expire_on_commit=False) as session:
        rows = list(session.scalars(select(HttpBridgeSessionRecord)))
        matching = [row for row in rows if row.session_key_value == session_key]
        assert len(matching) == 1, [(row.session_key_kind, row.session_key_value) for row in rows]
        session.expunge(matching[0])
        return matching[0]


async def _exercise_stale_owner_fence(old: HttpBridgeSessionRecord) -> None:
    engine = create_oracle_async_engine(_URL, pool_size=1, max_overflow=0)
    try:
        async with async_sessionmaker(engine)() as session:
            repository = DurableBridgeRepository(session)
            renewed = await repository.renew_session(
                session_id=old.id,
                instance_id="ha-a",
                owner_epoch=old.owner_epoch,
                lease_ttl_seconds=30,
                latest_response_id="resp_stale_owner_must_not_commit",
            )
            released = await repository.release_session(
                session_id=old.id, instance_id="ha-a", owner_epoch=old.owner_epoch, draining=False
            )
            assert renewed is not None and released is not None
            assert renewed.owner_instance_id == released.owner_instance_id == "ha-b"
            assert renewed.owner_epoch == released.owner_epoch > old.owner_epoch
            operations = list(
                await session.scalars(
                    select(HttpBridgeOperationRecord).where(HttpBridgeOperationRecord.session_id == old.id)
                )
            )
            operation = next(row for row in operations if row.response_id == "resp_bridge-takeover")
            deadline = time.monotonic() + 15
            while operation.terminal_append_phase == "pending":
                assert time.monotonic() < deadline, "The live successor did not settle its operation."
                await asyncio.sleep(0.05)
                await session.refresh(operation)
            assert operation.state == "completed" and operation.account_id == old.account_id
            before = tuple(getattr(operation, column.key) for column in inspect(HttpBridgeOperationRecord).columns)
            stale_settlement = await repository.update_operation(
                operation_id=operation.operation_id,
                session_id=old.id,
                instance_id="ha-a",
                owner_epoch=old.owner_epoch,
                state="failed",
                response_id="resp_stale_owner_must_not_settle",
            )
            assert stale_settlement is False
            await session.refresh(operation)
            after = tuple(getattr(operation, column.key) for column in inspect(HttpBridgeOperationRecord).columns)
            assert after == before
    finally:
        await engine.dispose()


def _await_line(lines: Iterator[str], marker: str, label: str) -> None:
    # A blocking stream read cannot be bounded by eventually(); report a
    # stalled or truncated stream under its step label instead.
    try:
        for line in lines:
            if marker in line:
                return
    except httpx.ReadTimeout as exc:
        raise AssertionError(f"Timed out waiting for {label}") from exc
    raise AssertionError(f"Stream ended before {label}")


def _choose(client: httpx.Client, gateway: Child, instance: str) -> None:
    def selected() -> bool:
        client.cookies.clear()
        return _json(client.get(gateway.url + "/__ha__/state"))["instance"] == instance

    eventually(f"gateway selects {instance}", selected)


def _warm_pools(cluster: Cluster, nodes: tuple[Child, ...], hold: str) -> int:
    def warm(node: Child) -> dict[str, int]:
        with httpx.Client(trust_env=False, timeout=45) as client:
            return _json(client.post(node.url + "/__ha__/warm-pools", params={"hold": hold}))

    with ThreadPoolExecutor(max_workers=len(nodes)) as executor:
        calls = [executor.submit(warm, node) for node in nodes]
        try:
            eventually(
                f"all {hold} processes hold pools",
                lambda: (
                    len([event for event in cluster.events("pool_slots_held") if event["hold"] == hold]) == len(nodes)
                ),
            )
            held = [event for event in cluster.events("pool_slots_held") if event["hold"] == hold]
            assert {event["pid"] for event in held} == {node.process.pid for node in nodes}
            assert all(event["request"] == 4 and event["background"] == 4 for event in held)
        finally:
            cluster.release(f"pools-{hold}")
        counts = [call.result(timeout=45) for call in calls]
        assert all(value == {"request": 4, "background": 4} for value in counts)
    # Holding every slot can fail readiness probes; let each process (and the
    # gateway's checks) recover before later steps route through it.
    for node in nodes:
        cluster.wait_ready(node, "/health/ready")
    return sum(sum(value.values()) for value in counts)


def _assert_singleton_nonoverlap(cluster: Cluster, deaths: dict[int, float]) -> None:
    events = sorted(
        cluster.events("singleton_start") + cluster.events("singleton_end"), key=lambda event: event["time"]
    )
    active: dict[int, float] = {}
    for event in events:
        active = {pid: started for pid, started in active.items() if deaths.get(pid, float("inf")) > event["time"]}
        if event["kind"] == "singleton_end":
            active.pop(event["pid"], None)
            continue
        assert not active, f"Singleton execution overlaps across processes: {active}, new={event}"
        active[event["pid"]] = event["time"]


def _accounting(engine: Engine, key_id: str, completed: int, *, pending: int = 0) -> bool:
    with Session(engine) as session:
        reservations = list(
            session.scalars(select(ApiKeyUsageReservation).where(ApiKeyUsageReservation.api_key_id == key_id))
        )
        assert sum(row.status == "finalized" for row in reservations) == completed
        assert sum(row.status == "reserved" for row in reservations) == pending
        reserved_ids = [row.id for row in reservations if row.status == "reserved"]
        reserved = sum(
            session.scalars(
                select(ApiKeyUsageReservationItem.reserved_delta).where(
                    ApiKeyUsageReservationItem.reservation_id.in_(reserved_ids)
                )
            )
        )
        assert (
            session.scalar(select(ApiKeyLimit.current_value).where(ApiKeyLimit.api_key_id == key_id))
            == completed * 5 + reserved
        )
        logs = list(session.scalars(select(RequestLog).where(RequestLog.api_key_id == key_id)))
        successful = [row for row in logs if row.input_tokens == 3 and row.output_tokens == 2]
        assert len(successful) == completed
        assert len({row.request_id for row in successful}) == completed
    return True


@pytest.mark.timeout(600)
def test_oracle_two_process_crash_retry_restart_and_drain(cluster: Cluster, schema_engine: Engine) -> None:
    try:
        _exercise_failover(cluster, schema_engine)
    except Exception as exc:
        pytest.fail(cluster.sanitize(f"{type(exc).__name__}: {exc}\n{cluster.logs()}"), pytrace=False)


def _exercise_failover(cluster: Cluster, engine: Engine) -> None:
    cluster.start_upstream()
    node_a = cluster.start_node("ha-a")
    node_b = cluster.start_node("ha-b")
    gateway = cluster.start_gateway()
    assert node_a.process.pid != node_b.process.pid
    timings: dict[str, float] = {}
    with httpx.Client(trust_env=False, timeout=90) as client:
        state_a = _json(client.get(node_a.url + "/__ha__/state"))
        state_b = _json(client.get(node_b.url + "/__ha__/state"))
        assert state_a["leader_id"] != state_b["leader_id"]
        original = state_b["cached_sticky"]
        _json(client.put(node_a.url + "/api/settings", json={"stickyThreadsEnabled": not original}))
        eventually(
            "peer cache invalidation",
            lambda: _json(client.get(node_b.url + "/__ha__/state"))["cached_sticky"] is not original,
            timeout=15,
        )
        auth = {
            "tokens": {
                "idToken": identity_token(),
                "accessToken": "oracle-ha-access",
                "refreshToken": "oracle-ha-refresh",
                "accountId": "oracle-ha-upstream",
            }
        }
        account = _json(
            client.post(
                node_a.url + "/api/accounts/import",
                files={"auth_json": ("auth.json", json.dumps(auth), "application/json")},
            )
        )["accountId"]
        key = _json(
            client.post(
                node_a.url + "/api/api-keys/",
                json={
                    "name": "oracle-ha-pilot",
                    "limits": [{"limitType": "total_tokens", "limitWindow": "weekly", "maxValue": 1_000_000}],
                },
            )
        )
        cluster.secrets.append(key["key"])
        _json(
            client.put(
                node_a.url + "/api/settings",
                json={
                    "routingStrategy": "single_account",
                    "singleAccountId": account,
                    "apiKeyAuthEnabled": True,
                },
            )
        )
        eventually(
            "peer routing settings",
            lambda: _json(client.get(node_b.url + "/__ha__/state"))["cached_account"] == account,
        )
        with Session(engine) as session:
            session.execute(
                update(Account).where(Account.id == account).values(last_refresh=utcnow() - timedelta(days=9))
            )
            session.commit()
        with ThreadPoolExecutor(max_workers=2) as executor:
            calls = [
                executor.submit(_complete, node.url, key["key"], f"refresh-{node.name}") for node in (node_a, node_b)
            ]
            for call in calls:
                call.result(timeout=100)
        assert len(cluster.events("token_exchange")) == 1, "Both processes exchanged a rotating token."
        completed = 2
        eventually("first two settlements", lambda: _accounting(engine, key["id"], completed))
        jobs = eventually("singleton executions", lambda: cluster.events("singleton_start"))
        assert {event["instance"] for event in jobs} == {"ha-a"}
        timings["steady_application_sessions"] = _warm_pools(cluster, (node_a, node_b), "steady")
        assert timings["steady_application_sessions"] == 16

        # A second HTTP connection reaching B must forward to A's existing
        # WebSocket and preserve both the durable account pin and response
        # anchor. Distinct wire connections would pass a status-only test.
        bridge_session = next(
            name
            for name in (f"oracle-ha-bridge-{index}" for index in range(100))
            if select_node(f"session_header:{name}:{key['id']}", ("ha-a", "ha-b")) == "ha-a"
        )
        _bridge_complete(node_a.url, key["key"], "bridge-first", session_key=bridge_session)
        _bridge_complete(
            node_b.url, key["key"], "bridge-forwarded", session_key=bridge_session, previous="bridge-first"
        )
        completed += 2
        first_owner = _bridge_record(engine, bridge_session)
        assert first_owner.owner_instance_id == "ha-a"
        assert first_owner.owner_process_epoch == state_a["bridge_process_epoch"]
        assert first_owner.account_id == account
        assert first_owner.latest_response_id == "resp_bridge-forwarded"
        bridge_events = [event for event in cluster.events("upstream_start") if event["request"].startswith("bridge-")]
        assert len(bridge_events) == 2
        assert bridge_events[0]["connection"] == bridge_events[1]["connection"] != "http"
        eventually("forwarded settlements exactly once", lambda: _accounting(engine, key["id"], completed))

        # HAProxy's ordinary affinity cookie pins this stream to the known
        # leader so one SIGKILL proves both serving-process and leader loss.
        _choose(client, gateway, "ha-a")
        with client.stream(
            "POST",
            gateway.url + "/backend-api/codex/responses",
            headers={"Authorization": f"Bearer {key['key']}"},
            json=_payload("hold-crash"),
        ) as response:
            assert response.status_code == 200
            assert response.headers["x-ha-test-backend"] == "ha-a"
            lines = response.iter_lines()
            _await_line(lines, '"response.created"', "first streamed event")
            killed_at = time.monotonic()
            node_a.kill()
            try:
                assert not any('"response.completed"' in line for line in lines)
            except (httpx.RemoteProtocolError, httpx.ReadError):
                pass
        eventually(
            "surviving gateway backend",
            lambda: _json(client.get(gateway.url + "/__ha__/state"))["instance"] == "ha-b",
            timeout=15,
        )
        timings["routing_failover_seconds"] = time.monotonic() - killed_at
        cluster.release("hold-crash")
        retry = _complete(gateway.url, key["key"], "hold-crash")
        assert retry.headers["x-ha-test-backend"] == "ha-b"
        completed += 1
        eventually("survivor settlements", lambda: _accounting(engine, key["id"], completed, pending=1))
        eventually(
            "scheduler takeover",
            lambda: any(
                event["instance"] == "ha-b" and event["time"] > killed_at for event in cluster.events("singleton_start")
            ),
            timeout=45,
        )
        timings["leader_takeover_seconds"] = time.monotonic() - killed_at

        def bridge_lease_expired() -> bool:
            lease = _bridge_record(engine, bridge_session).lease_expires_at
            return lease is not None and to_utc_naive(lease) <= utcnow()

        eventually(
            "dead bridge owner's normal lease expiry",
            bridge_lease_expired,
            timeout=45,
        )
        _bridge_complete(
            node_b.url, key["key"], "bridge-takeover", session_key=bridge_session, previous="bridge-forwarded"
        )
        completed += 1
        successor = _bridge_record(engine, bridge_session)
        assert successor.id == first_owner.id
        assert successor.owner_instance_id == "ha-b"
        assert successor.owner_epoch > first_owner.owner_epoch
        assert successor.owner_process_epoch == state_b["bridge_process_epoch"]
        assert successor.account_id == account
        assert successor.latest_response_id == "resp_bridge-takeover"
        asyncio.run(_exercise_stale_owner_fence(first_owner))
        fenced = _bridge_record(engine, bridge_session)
        assert fenced.owner_epoch == successor.owner_epoch
        assert fenced.latest_response_id == successor.latest_response_id
        assert fenced.owner_instance_id == "ha-b" and fenced.account_id == account
        timings["bridge_takeover_seconds"] = time.monotonic() - killed_at
        eventually("bridge takeover settlement", lambda: _accounting(engine, key["id"], completed, pending=1))

        # Run the production scheduler on the survivor. Recent uncertain work
        # stays reserved; advancing only our orphan row's timestamps then
        # exercises the unchanged six-hour expiry policy without waiting six hours.
        _json(client.post(node_b.url + "/__ha__/reset-limits"))
        _accounting(engine, key["id"], completed, pending=1)
        with Session(engine) as session:
            orphan = session.scalar(
                select(ApiKeyUsageReservation).where(
                    ApiKeyUsageReservation.api_key_id == key["id"], ApiKeyUsageReservation.status == "reserved"
                )
            )
            assert orphan is not None
            orphan_id = orphan.id
            session.execute(
                update(ApiKeyUsageReservation)
                .where(ApiKeyUsageReservation.id == orphan_id)
                .values(created_at=utcnow() - timedelta(hours=7), updated_at=utcnow() - timedelta(hours=7))
            )
            session.commit()
        _json(client.post(node_b.url + "/__ha__/reset-limits"))
        eventually("orphan reclaimed once", lambda: _accounting(engine, key["id"], completed))
        _json(client.post(node_b.url + "/__ha__/reset-limits"))
        _accounting(engine, key["id"], completed)

        restarted = cluster.start_node("ha-a")
        assert restarted.process.pid != node_a.process.pid
        restarted_state = _json(client.get(restarted.url + "/__ha__/state"))
        assert restarted_state["leader_id"] != state_a["leader_id"]
        assert restarted_state["bridge_process_epoch"] != state_a["bridge_process_epoch"]
        _bridge_complete(
            restarted.url, key["key"], "bridge-after-restart", session_key=bridge_session, previous="bridge-takeover"
        )
        completed += 1
        current_owner = _bridge_record(engine, bridge_session)
        assert current_owner.id == successor.id
        assert current_owner.owner_instance_id == "ha-b" and current_owner.owner_epoch == successor.owner_epoch
        assert current_owner.owner_process_epoch == successor.owner_process_epoch
        assert current_owner.account_id == account
        after_restart = [
            event for event in cluster.events("upstream_start") if event["request"] == "bridge-after-restart"
        ]
        takeover = [event for event in cluster.events("upstream_start") if event["request"] == "bridge-takeover"]
        assert after_restart[0]["connection"] == takeover[0]["connection"] != bridge_events[0]["connection"]
        _complete(restarted.url, key["key"], "after-restart")
        completed += 1
        replacement = cluster.start_node("ha-c")
        timings["overlap_application_sessions"] = _warm_pools(cluster, (restarted, node_b, replacement), "overlap")
        assert timings["overlap_application_sessions"] == 24

        _choose(client, gateway, "ha-b")
        with client.stream(
            "POST",
            gateway.url + "/backend-api/codex/responses",
            headers={"Authorization": f"Bearer {key['key']}"},
            json=_payload("hold-drain"),
        ) as response:
            assert response.status_code == 200 and response.headers["x-ha-test-backend"] == "ha-b"
            lines = response.iter_lines()
            _await_line(lines, '"response.created"', "accepted drain stream")
            _json(client.post(node_b.url + "/internal/drain/start"))
            assert client.get(node_b.url + "/health/ready").status_code == 503
            eventually(
                "drained backend excluded",
                lambda: _json(client.get(gateway.url + "/__ha__/state"))["instance"] != "ha-b",
            )
            cluster.release("hold-drain")
            assert any('"response.completed"' in line for line in lines)
        completed += 1
        eventually("drained stream settled", lambda: _accounting(engine, key["id"], completed))
        node_b.stop()
        stopped_at = time.monotonic()
        _complete(gateway.url, key["key"], "after-drain")
        completed += 1
        eventually("final settlements", lambda: _accounting(engine, key["id"], completed))
        _assert_singleton_nonoverlap(cluster, {node_a.process.pid: killed_at, node_b.process.pid: stopped_at})
        with Session(engine) as session:
            reclaimed = session.get(ApiKeyUsageReservation, orphan_id)
            assert reclaimed is not None and reclaimed.status == "released"
        print("oracle_ha_acceptance=" + json.dumps(timings, sort_keys=True), flush=True)
