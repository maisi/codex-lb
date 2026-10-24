from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.crypto import TokenEncryptor
from app.core.exceptions import DashboardRateLimitError
from app.core.rate_limiter.db_rate_limiter import DatabaseRateLimiter
from app.db.models import (
    Account,
    AccountStatus,
    ApiKey,
    ApiKeyLimit,
    Base,
    LimitType,
    LimitWindow,
    OAuthDeviceFlowSlot,
    RequestLog,
    StickySessionKind,
    UsageHistory,
)
from app.db.oracle_baseline import apply_oracle_baseline
from app.db.oracle_connection import create_oracle_async_engine
from app.modules.accounts.repository import AccountsRepository
from app.modules.api_keys.repository import ApiKeysRepository, UsageReservationItemData
from app.modules.oauth.repository import OAuthFlowRepository
from app.modules.proxy.durable_bridge_repository import DurableBridgeRepository, missing_durable_bridge_tables
from app.modules.proxy.ring_membership import RingMembershipService
from app.modules.proxy.sticky_repository import StickySessionsRepository
from app.modules.quota_planner.repository import QuotaPlannerRepository
from app.modules.request_logs.repository import RequestLogsRepository
from app.modules.settings.repository import ModelContextWindowOverridesRepository
from app.modules.usage.repository import UsageRepository

_ORACLE_URL = os.environ.get("CODEX_LB_TEST_ORACLE_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _ORACLE_URL, reason="Set CODEX_LB_TEST_ORACLE_URL to an empty owned Oracle test schema."),
]


@pytest.fixture
async def oracle_runtime() -> AsyncIterator[AsyncEngine]:
    pytest.importorskip("oracledb")
    engine = create_oracle_async_engine(_ORACLE_URL, pool_size=4, max_overflow=0)
    created = False
    try:
        async with engine.begin() as connection:
            tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
            if tables:
                pytest.fail("Oracle runtime tests require an empty owned schema; existing tables are preserved.")
            created = True
            await connection.run_sync(apply_oracle_baseline)
        yield engine
    finally:
        try:
            if created:
                async with engine.begin() as connection:
                    await connection.run_sync(Base.metadata.drop_all)
        finally:
            await engine.dispose()


def _account() -> Account:
    return Account(
        id="oracle-runtime-account",
        chatgpt_account_id="oracle-upstream-account",
        email="oracle@example.invalid",
        plan_type="plus",
        access_token_encrypted=b"access",
        refresh_token_encrypted=b"refresh",
        id_token_encrypted=b"identity",
        last_refresh=datetime(2026, 10, 24, 10, 15, 1, 123456),
        status=AccountStatus.ACTIVE,
    )


async def test_oracle_account_import_sticky_oauth_and_planner(oracle_runtime: AsyncEngine) -> None:
    factory = async_sessionmaker(oracle_runtime, expire_on_commit=False)
    async with factory() as session:
        accounts = AccountsRepository(session)
        account = await accounts.upsert(_account(), merge_by_email=True)
        assert account.last_refresh.microsecond == 123456
        assert not await accounts.rotate_tokens(
            account.id,
            b"new-access",
            b"new-refresh",
            b"new-identity",
            account.last_refresh,
            expected_refresh_token_encrypted=b"stale-refresh",
        )
        assert await accounts.rotate_tokens(
            account.id,
            b"new-access",
            b"new-refresh",
            b"new-identity",
            account.last_refresh,
            expected_refresh_token_encrypted=b"refresh",
        )
        sticky = StickySessionsRepository(session)
        row = await sticky.upsert_with_seed_if_absent(
            "thread",
            account.id,
            kind=StickySessionKind.PROMPT_CACHE,
            seed_key="seed",
            seed_kind=StickySessionKind.PROMPT_CACHE,
        )
        assert row.account_id == account.id
        assert (
            await sticky.insert_if_absent("thread", "nonexistent-account", StickySessionKind.PROMPT_CACHE) == account.id
        )
        oauth = OAuthFlowRepository(session, TokenEncryptor(key=Fernet.generate_key()))
        await oauth.claim_device_slot("first")
        await oauth.claim_device_slot("second")
        slot = await session.get(OAuthDeviceFlowSlot, "dashboard")
        assert slot is not None and slot.generation == 2
        assert not await oauth.consume_device_slot("first")
        assert await oauth.consume_device_slot("second")
        planner = QuotaPlannerRepository(session)
        decision = await planner.log_decision(
            mode="active", action="warmup", idempotency_key="single", account_id=account.id
        )
        repeated = await planner.log_decision(
            mode="active", action="warmup", idempotency_key="single", account_id=account.id
        )
        assert repeated.id == decision.id
        assert (
            await planner.claim_warmup_decision(
                decision.id,
                since=datetime(2026, 1, 1),
                max_warmups=1,
                max_credits=100,
            )
            is not None
        )

    async def override(value: int) -> None:
        async with factory() as session:
            await ModelContextWindowOverridesRepository(session).upsert("oracle-model", value)

    await asyncio.gather(override(16384), override(32768))
    async with factory() as session:
        assert (await ModelContextWindowOverridesRepository(session).by_slug())["oracle-model"] in {16384, 32768}


async def test_oracle_reservation_settlement_and_auth_rate_limit(oracle_runtime: AsyncEngine) -> None:
    factory = async_sessionmaker(oracle_runtime, expire_on_commit=False)
    reset_at = datetime(2026, 10, 25)
    async with factory() as session:
        repo = ApiKeysRepository(session)
        await repo.create(ApiKey(id="oracle-key", name="Oracle", key_hash="hash", key_prefix="sk-test"))
        limit = ApiKeyLimit(
            api_key_id="oracle-key",
            limit_type=LimitType.TOTAL_TOKENS,
            limit_window=LimitWindow.DAILY,
            max_value=100,
            current_value=0,
            reset_at=reset_at,
        )
        session.add(limit)
        await session.commit()
        item = UsageReservationItemData(
            limit_id=limit.id,
            limit_type=LimitType.TOTAL_TOKENS,
            reserved_delta=40,
            expected_reset_at=reset_at,
        )
        assert (await repo.try_reserve_usage(limit.id, delta=40, expected_reset_at=reset_at)).success
        await repo.create_usage_reservation(
            "oracle-reservation", key_id="oracle-key", model="oracle-model", items=[item]
        )
        await session.commit()
        assert not (await repo.try_reserve_usage(limit.id, delta=61, expected_reset_at=reset_at)).success
        assert await repo.transition_usage_reservation_status(
            "oracle-reservation", expected_status="reserved", new_status="settling"
        )
        assert await repo.adjust_reserved_usage(limit.id, delta=-10, expected_reset_at=reset_at)
        await repo.upsert_reservation_item_actual("oracle-reservation", item=item, actual_delta=30)
        await repo.settle_usage_reservation(
            "oracle-reservation",
            status="settled",
            input_tokens=20,
            output_tokens=10,
            cached_input_tokens=0,
            cost_microdollars=100,
        )
        await session.commit()
        reservation = await repo.get_usage_reservation("oracle-reservation")
        assert reservation is not None and reservation.status == "settled"
        assert reservation.items[0].actual_delta == 30
        await session.refresh(limit)
        assert limit.current_value == 30
        limiter = DatabaseRateLimiter(max_attempts=1, window_seconds=60, type="oracle-login")
        await limiter.check_and_increment("ip", session)
        with pytest.raises(DashboardRateLimitError):
            await limiter.check_and_increment("ip", session)


async def test_oracle_dashboard_trends_and_filters(oracle_runtime: AsyncEngine) -> None:
    factory = async_sessionmaker(oracle_runtime, expire_on_commit=False)
    at = datetime(2026, 10, 24, 10, 15, 1, 654321)
    async with factory() as session:
        account = await AccountsRepository(session).upsert(_account(), merge_by_email=True)
        session.add_all(
            [
                RequestLog(
                    account_id=account.id,
                    request_id="oracle-request",
                    model="oracle-model",
                    status="success",
                    requested_at=at,
                    input_tokens=10,
                    cached_input_tokens=20,
                    output_tokens=5,
                    cost_usd=0.01,
                    reasoning_effort="",
                    conversation_id="conversation",
                ),
                UsageHistory(account_id=account.id, recorded_at=at, window="primary", used_percent=25),
            ]
        )
        await session.commit()
        logs = RequestLogsRepository(session)
        buckets = await logs.aggregate_by_bucket(at - timedelta(hours=1), bucket_seconds=3600)
        assert len(buckets) == 1
        assert buckets[0].bucket_epoch == int(
            at.replace(tzinfo=timezone.utc, minute=0, second=0, microsecond=0).timestamp()
        )
        filters = await logs.list_filter_options()
        assert filters[0] == [account.id]
        assert filters[1] == [("oracle-model", "")]
        usage = await UsageRepository(session).trends_by_bucket(at - timedelta(hours=1), bucket_seconds=3600)
        assert len(usage) == 1
        assert usage[0].avg_used_percent == 25

        from app.modules.accounts.usage_rollup import _fold_next_slice
        from app.modules.accounts.usage_time_rollup import _fold_next_conversation_slice, _fold_next_hourly_slice
        from app.modules.reports.rollup import fold_next_report_slice

        target = at.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        for fold in (_fold_next_slice, _fold_next_hourly_slice, _fold_next_conversation_slice):
            await fold(session, target)
        assert await fold_next_report_slice(session, target)
        folded = await logs.aggregate_by_bucket(at - timedelta(hours=1), bucket_seconds=3600)
        assert len(folded) == 1
        assert folded[0].bucket_epoch == buckets[0].bucket_epoch


async def test_oracle_bridge_continuity_and_retry_lineage(oracle_runtime: AsyncEngine) -> None:
    factory = async_sessionmaker(oracle_runtime, expire_on_commit=False)
    ring = RingMembershipService(factory)
    await ring.register("single", endpoint_base_url="http://single.invalid")
    assert await ring.resolve_endpoint("single") == "http://single.invalid"
    await ring.unregister("single")
    await ring.heartbeat("single", endpoint_base_url="http://single.invalid")
    assert len(await ring.list_active()) == 1
    async with factory() as session:
        assert await missing_durable_bridge_tables(session) == ()
        bridge = DurableBridgeRepository(session)
        claimed = await bridge.claim_session(
            session_key_kind="session_header",
            session_key_value="bridge-thread",
            api_key_scope="",
            instance_id="single",
            owner_process_epoch="process",
            lease_ttl_seconds=30,
            account_id=None,
            model="oracle-model",
            service_tier=None,
            latest_turn_state="turn" * 2048,
            latest_response_id="response",
            allow_takeover=False,
        )
        found = await bridge.find_session_by_latest_turn_state(turn_state="turn" * 2048, api_key_scope="")
        assert found is not None and found.id == claimed.id
        await bridge.upsert_alias(
            session_id=claimed.id, alias_kind="turn_state", alias_value="turn" * 2048, api_key_scope=""
        )
        alias = await bridge.resolve_alias(alias_kind="turn_state", alias_value="turn" * 2048, api_key_scope="")
        assert alias is not None and alias.id == claimed.id
        await bridge.upsert_retry_circuit(
            session_key_kind="session_header",
            session_key_value="bridge-thread",
            api_key_scope="",
            consecutive_failures=1,
            cooldown_until_epoch=0,
            last_detail="clean_close",
            updated_at_epoch=10,
            failure_threshold=2,
        )
        await bridge.upsert_retry_circuit(
            session_key_kind="session_header",
            session_key_value="bridge-thread",
            api_key_scope="",
            consecutive_failures=2,
            cooldown_until_epoch=0,
            last_detail="stream_incomplete",
            updated_at_epoch=20,
            base_updated_at_epoch=10,
            failure_threshold=2,
        )
        await bridge.upsert_retry_circuit(
            session_key_kind="session_header",
            session_key_value="bridge-thread",
            api_key_scope="",
            consecutive_failures=3,
            cooldown_until_epoch=1000,
            last_detail="clean_close",
            updated_at_epoch=30,
            base_updated_at_epoch=10,
            failure_threshold=2,
        )
        circuit = await bridge.get_retry_circuit(
            session_key_kind="session_header", session_key_value="bridge-thread", api_key_scope=""
        )
        assert circuit is not None and circuit.consecutive_failures == 2
        assert circuit.updated_at_epoch == 20
        assert circuit.cooldown_until_epoch == 80
        assert circuit.last_detail == "stream_incomplete"
