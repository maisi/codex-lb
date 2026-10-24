"""Subprocess smoke using the real application lifecycle and an owned schema."""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


class _NoNetworkScheduler:
    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


# These loops call external services (including configured automations and
# quota warmups). Keep DB-only maintenance and the real leader/ring/cache
# lifecycle running; never send imported fake credentials to an upstream.
_NETWORK_SCHEDULER_BUILDERS = (
    "build_metadata_refresh_scheduler",
    "build_usage_refresh_scheduler",
    "build_model_refresh_scheduler",
    "build_auth_guardian_scheduler",
    "build_automations_scheduler",
    "build_rate_limit_reset_credits_scheduler",
    "build_quota_planner_scheduler",
    "build_telemetry_scheduler",
)


async def main() -> None:
    import app.main as app_main
    import app.modules.usage.updater as usage_updater
    from app.core.usage.models import UsagePayload
    from app.db.models import ApiKeyLimit, RequestLog
    from app.db.session import SessionLocal
    from app.modules.proxy import service as proxy_service

    for builder in _NETWORK_SCHEDULER_BUILDERS:
        setattr(app_main, builder, _NoNetworkScheduler)
    create_app = app_main.create_app

    suffix = uuid4().hex[:12]
    upstream_id = f"oracle_smoke_{suffix}"
    payload = {
        "email": f"oracle-{suffix}@example.invalid",
        "https://api.openai.com/auth": {"chatgpt_plan_type": "plus"},
    }
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    auth = {
        "tokens": {
            "idToken": f"header.{body}.signature",
            "accessToken": "oracle-smoke-access",
            "refreshToken": "oracle-smoke-refresh",
            "accountId": upstream_id,
        }
    }

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

    async def fake_stream(*args: Any, **kwargs: Any) -> AsyncIterator[str]:
        yield (
            'data: {"type":"response.completed","response":{"id":"resp_oracle_smoke",'
            '"usage":{"input_tokens":3,"output_tokens":2,"total_tokens":5}}}\n\n'
        )

    # Upstream calls and network-facing schedulers are stubbed. Database
    # startup, dependencies, DB-only backgrounds and shutdown remain real.
    setattr(proxy_service, "core_stream_responses", fake_stream)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            result = await client.get("/api/settings")
            assert result.status_code == 200, (result.status_code, result.text)
            original = result.json()["stickyThreadsEnabled"]
            original_settings = {
                name: result.json()[name]
                for name in ("stickyThreadsEnabled", "routingStrategy", "singleAccountId", "apiKeyAuthEnabled")
            }
            result = await client.put("/api/settings", json={"stickyThreadsEnabled": not original})
            assert result.status_code == 200, (result.status_code, result.text)
            result = await client.post(
                "/api/accounts/import", files={"auth_json": ("auth.json", json.dumps(auth), "application/json")}
            )
            assert result.status_code == 200, (result.status_code, result.text)
            account_id = result.json()["accountId"]
            result = await client.get("/api/accounts")
            assert result.status_code == 200, (result.status_code, result.text)
            assert account_id in {item["accountId"] for item in result.json()["accounts"]}
            result = await client.post(
                "/api/api-keys/",
                json={
                    "name": f"oracle-{suffix}",
                    "limits": [{"limitType": "total_tokens", "limitWindow": "weekly", "maxValue": 1_000_000}],
                },
            )
            assert result.status_code == 200, (result.status_code, result.text)
            key_id = result.json()["id"]
            api_key = result.json()["key"]
            result = await client.put(
                "/api/settings",
                json={
                    "routingStrategy": "single_account",
                    "singleAccountId": account_id,
                    "apiKeyAuthEnabled": True,
                },
            )
            assert result.status_code == 200, (result.status_code, result.text)
            result = await client.post(
                "/backend-api/codex/responses",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True},
            )
            assert result.status_code == 200, (result.status_code, result.text)
            assert '"response.completed"' in result.text, result.text
            service = app.state.proxy_service
            assert await service.drain_persistence_tasks(timeout_seconds=15)
            async with SessionLocal() as session:
                log = await session.scalar(select(RequestLog).where(RequestLog.account_id == account_id))
                assert log is not None and log.input_tokens == 3 and log.output_tokens == 2
                assert log.api_key_id == key_id
                limit = await session.scalar(select(ApiKeyLimit).where(ApiKeyLimit.api_key_id == key_id))
                assert limit is not None and limit.current_value == 5
            for route in ("/api/dashboard/overview", "/api/request-logs", "/api/api-keys/", "/api/settings"):
                result = await client.get(route)
                assert result.status_code == 200, (route, result.status_code, result.text)
            print("oracle_application_startup_api_and_proxy_persistence=ok", flush=True)

    # A second real lifespan must use the installed schema and stored settings,
    # accounts, key and logs rather than replacing them on startup.
    app = create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            result = await client.get("/api/settings")
            assert result.status_code == 200 and result.json()["stickyThreadsEnabled"] is not original
            accounts = await client.get("/api/accounts")
            assert accounts.status_code == 200
            assert account_id in {item["accountId"] for item in accounts.json()["accounts"]}
            keys = await client.get("/api/api-keys/")
            assert keys.status_code == 200 and key_id in {item["id"] for item in keys.json()}
            result = await client.put("/api/settings", json=original_settings)
            assert result.status_code == 200
    print("oracle_application_restart_and_shutdown=ok", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
