"""Test-only TCP workers; coordination, application APIs and storage stay real."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import time
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, cast

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy.pool import QueuePool


def append_event(directory: Path, kind: str, **values: Any) -> None:
    event = json.dumps({"kind": kind, "pid": os.getpid(), "time": time.monotonic(), **values}) + "\n"
    descriptor = os.open(directory / "events.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(descriptor, event.encode())
    finally:
        os.close(descriptor)


def identity_token() -> str:
    claims = {
        "email": "oracle-ha@example.invalid",
        "https://api.openai.com/auth": {"chatgpt_plan_type": "plus"},
    }
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"header.{body}.signature"


def upstream_app(directory: Path) -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    async def events(payload: dict[str, Any], connection: str = "http") -> AsyncIterator[dict[str, Any]]:
        name = str(payload.get("instructions", "request"))
        assert name.replace("-", "").isalnum(), "Only fixture-controlled request names are allowed."
        append_event(directory, "upstream_start", request=name, connection=connection)
        response_id = f"resp_{name}"
        yield {"type": "response.created", "response": {"id": response_id, "status": "in_progress"}}
        if name.startswith("hold-"):
            while not (directory / f"release-{name}").exists():
                await asyncio.sleep(0.05)
        yield {
            "type": "response.completed",
            "response": {
                "id": response_id,
                "status": "completed",
                "output": [],
                "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            },
        }
        append_event(directory, "upstream_complete", request=name)

    @app.post("/backend-api/codex/responses")
    async def responses(payload: dict[str, Any]) -> StreamingResponse:
        async def stream() -> AsyncIterator[str]:
            async for event in events(payload):
                yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.websocket("/backend-api/codex/responses")
    async def websocket_responses(socket: WebSocket) -> None:
        await socket.accept()
        try:
            while True:
                payload = await socket.receive_json()
                async for event in events(payload, connection=str(socket.client)):
                    await socket.send_json(event)
        except (WebSocketDisconnect, OSError):
            # Peer termination is expected when an application is SIGKILLed;
            # anything else propagates to this worker's log for diagnosis.
            return

    @app.post("/oauth/token")
    async def refresh(payload: dict[str, Any]) -> dict[str, Any]:
        assert payload["grant_type"] == "refresh_token"
        append_event(directory, "token_exchange")
        await asyncio.sleep(1)
        return {
            "access_token": "oracle-ha-access-rotated",
            "refresh_token": "oracle-ha-refresh-rotated",
            "id_token": identity_token(),
            "token_type": "Bearer",
            "expires_in": 3600,
        }

    return app


def node_app(directory: Path, upstream: str) -> FastAPI:
    import app.core.auth.refresh as refresh_module
    import app.main as app_main
    import app.modules.usage.updater as usage_updater
    from app.core.config.settings import get_settings
    from app.core.config.settings_cache import get_settings_cache
    from app.core.scheduling.leader_election import get_leader_election
    from app.core.usage.metadata_scheduler import MetadataRefreshScheduler
    from app.core.usage.models import UsagePayload
    from app.db import session as db_session
    from app.modules.proxy.durable_bridge_runtime import http_bridge_owner_process_epoch

    class NoNetworkScheduler:
        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

    for builder in (
        "build_usage_refresh_scheduler",
        "build_model_refresh_scheduler",
        "build_auth_guardian_scheduler",
        "build_automations_scheduler",
        "build_rate_limit_reset_credits_scheduler",
        "build_quota_planner_scheduler",
        "build_telemetry_scheduler",
    ):
        setattr(app_main, builder, NoNetworkScheduler)

    # Only external metadata fetch is suppressed; the production scheduler's
    # run_if_leader -> real cost backfill path executes in both processes.
    async def no_external_metadata(self: MetadataRefreshScheduler) -> None:
        self._refresh_at = time.monotonic() + 3600

    original_backfill = MetadataRefreshScheduler._backfill

    async def tracked_backfill(self: MetadataRefreshScheduler) -> bool:
        instance = get_settings().http_responses_session_bridge_instance_id
        append_event(directory, "singleton_start", instance=instance)
        try:
            return await original_backfill(self)
        finally:
            self._backfill_at = 0
            append_event(directory, "singleton_end", instance=instance)

    MetadataRefreshScheduler._refresh = no_external_metadata
    MetadataRefreshScheduler._backfill = tracked_backfill
    setattr(app_main, "build_metadata_refresh_scheduler", lambda: MetadataRefreshScheduler(interval_seconds=0.5))
    setattr(refresh_module, "AUTH_BASE_URL", upstream)
    # A peer cache must observe invalidation rather than merely a five-second
    # TTL expiry. This test-only TTL is never installed in product settings.
    get_settings_cache()._ttl_seconds = 60

    async def fake_usage(**kwargs: Any) -> UsagePayload:
        return UsagePayload.model_validate(
            {
                "plan_type": "plus",
                "rate_limit": {
                    "primary_window": {"used_percent": 1, "limit_window_seconds": 18000, "reset_after_seconds": 3600},
                    "secondary_window": {
                        "used_percent": 1,
                        "limit_window_seconds": 604800,
                        "reset_after_seconds": 604800,
                    },
                },
            }
        )

    setattr(usage_updater, "fetch_usage", fake_usage)
    app = app_main.create_app()

    @app.get("/__ha__/state")
    async def state() -> dict[str, Any]:
        settings = get_settings()
        cache = await get_settings_cache().get()
        election = get_leader_election()
        return {
            "instance": settings.http_responses_session_bridge_instance_id,
            "pid": os.getpid(),
            "leader_id": election.leader_id,
            "bridge_process_epoch": http_bridge_owner_process_epoch(),
            "is_leader": election.is_leader,
            "cached_sticky": cache.sticky_threads_enabled,
            "cached_account": cache.single_account_id,
        }

    @app.post("/__ha__/warm-pools")
    async def warm_pools(hold: str) -> dict[str, int]:
        # Hold all physical slots simultaneously, proving each process has
        # both independent pools and no overflow, rather than multiplying a
        # configured number without opening real connections.
        background = db_session._background_engine
        assert background is not None
        async with AsyncExitStack() as stack:
            for engine in (db_session.engine, background):
                for _ in range(4):
                    await stack.enter_async_context(engine.connect())
            counts = {
                "request": cast(QueuePool, db_session.engine.pool).checkedout(),
                "background": cast(QueuePool, background.pool).checkedout(),
            }
            assert hold in {"steady", "overlap"}
            append_event(
                directory,
                "pool_slots_held",
                instance=get_settings().http_responses_session_bridge_instance_id,
                hold=hold,
                **counts,
            )
            deadline = time.monotonic() + 30
            while not (directory / f"release-pools-{hold}").exists():
                assert time.monotonic() < deadline, "Pool overlap barrier was not released."
                await asyncio.sleep(0.05)
            return counts

    @app.post("/__ha__/reset-limits")
    async def reset_limits() -> dict[str, str]:
        from app.modules.api_keys.reset_scheduler import ApiKeyLimitResetScheduler

        await ApiKeyLimitResetScheduler(interval_seconds=3600, enabled=True)._reset_once()
        return {"status": "ok"}

    # create_app installs its SPA catch-all last. Keep only these test-only
    # observability routes ahead of it, without changing product routing.
    app.router.routes[:] = app.router.routes[-3:] + app.router.routes[:-3]
    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=("upstream", "node"))
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--upstream", default="")
    args = parser.parse_args()
    app = upstream_app(args.control) if args.role == "upstream" else node_app(args.control, args.upstream)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
