from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Literal

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import inspect, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.crypto import TokenEncryptor
from app.core.exceptions import DashboardRateLimitError
from app.core.rate_limiter.db_rate_limiter import DatabaseRateLimiter
from app.db.models import (
    HTTP_BRIDGE_SPOOL_FORMAT_CHUNKS_V2,
    HTTP_BRIDGE_SPOOL_FORMAT_ROWS_V1,
    Account,
    AccountStatus,
    ApiKey,
    ApiKeyLimit,
    Base,
    HttpBridgeOperationEvent,
    HttpBridgeOperationEventChunk,
    HttpBridgeOperationRecord,
    HttpBridgeSessionRecord,
    LimitType,
    LimitWindow,
    OAuthDeviceFlowSlot,
    RequestConversationHourlyRollup,
    RequestLog,
    RequestReportHourlyRollup,
    RequestUsageHourlyRollup,
    StickySessionKind,
    UsageHistory,
)
from app.db.oracle_baseline import apply_oracle_baseline
from app.db.oracle_connection import create_oracle_async_engine, create_oracle_sync_engine
from app.modules.accounts.repository import AccountsRepository
from app.modules.api_keys.repository import ApiKeysRepository, UsageReservationItemData
from app.modules.oauth.repository import OAuthFlowRepository
from app.modules.proxy.durable_bridge_repository import DurableBridgeRepository, missing_durable_bridge_tables
from app.modules.proxy.durable_bridge_transcript_codec import encode_durable_bridge_transcript_chunk
from app.modules.proxy.ring_membership import RingMembershipService
from app.modules.proxy.sticky_repository import StickySessionsRepository
from app.modules.quota_planner.repository import QuotaPlannerRepository
from app.modules.request_logs.cost_backfill import backfill_missing_costs
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
    schema_engine = create_oracle_sync_engine(_ORACLE_URL, poolclass=NullPool)
    created = False

    def install_schema() -> None:
        nonlocal created
        with schema_engine.begin() as connection:
            if inspect(connection).get_table_names():
                pytest.fail("Oracle runtime tests require an empty owned schema; existing tables are preserved.")
            created = True
            apply_oracle_baseline(connection)

    def remove_schema() -> None:
        with schema_engine.begin() as connection:
            Base.metadata.drop_all(connection)

    try:
        # Match production migration connections and their DDL timeout; the
        # application pool retains its shorter runtime operation deadline.
        await asyncio.to_thread(install_schema)
        yield engine
    finally:
        try:
            await engine.dispose()
        finally:
            try:
                if created:
                    await asyncio.to_thread(remove_schema)
            finally:
                schema_engine.dispose()


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


@pytest.mark.parametrize("owner_end", ["expire", "release"])
async def test_oracle_bridge_purge_limits_batches_and_preserves_active_operations(
    oracle_runtime: AsyncEngine, owner_end: Literal["expire", "release"]
) -> None:
    factory = async_sessionmaker(oracle_runtime, expire_on_commit=False)
    cutoff = datetime(2021, 1, 1, tzinfo=timezone.utc)
    terminal_ids = {"old-completed", "old-incomplete", "old-failed"}
    active_ids = {"old-submitted", "old-acknowledged", "old-unknown"}
    async with factory() as session:
        bridge = DurableBridgeRepository(session)
        owner = await bridge.claim_session(
            session_key_kind="session_header",
            session_key_value="purge-thread",
            api_key_scope="",
            instance_id="single",
            owner_process_epoch="process",
            lease_ttl_seconds=3600,
            account_id=None,
            model="oracle-model",
            service_tier=None,
            latest_turn_state=None,
            latest_response_id=None,
            allow_takeover=False,
        )
        states = ("submitted", "acknowledged", "unknown", "completed", "incomplete", "failed", "completed")
        for index, state in enumerate(states):
            operation_id = "recent" if index == 6 else f"old-{state}"
            event_text = f"data: {operation_id}\n\n"
            updated_at = datetime(2022 if index == 6 else 2000, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=index)
            chunked = index % 2 == 0
            session.add(
                HttpBridgeOperationRecord(
                    operation_id=operation_id,
                    session_id=owner.id,
                    request_fingerprint=operation_id,
                    state=state,
                    updated_at=updated_at,
                    event_bytes=len(event_text.encode()),
                    spool_format=HTTP_BRIDGE_SPOOL_FORMAT_CHUNKS_V2 if chunked else HTTP_BRIDGE_SPOOL_FORMAT_ROWS_V1,
                )
            )
            await session.flush()
            if chunked:
                encoded = encode_durable_bridge_transcript_chunk([event_text])
                session.add(
                    HttpBridgeOperationEventChunk(
                        operation_id=operation_id,
                        first_sequence_number=1,
                        event_count=encoded.event_count,
                        codec=encoded.codec,
                        uncompressed_bytes=encoded.uncompressed_bytes,
                        payload=encoded.payload,
                        payload_sha256=encoded.payload_sha256,
                    )
                )
            else:
                session.add(
                    HttpBridgeOperationEvent(
                        operation_id=operation_id,
                        sequence_number=1,
                        event_fingerprint=operation_id,
                        event_text=event_text,
                    )
                )
        await session.commit()

        async def assert_remaining(expected: set[str]) -> None:
            assert set(await session.scalars(select(HttpBridgeOperationRecord.operation_id))) == expected
            rows = set(await session.scalars(select(HttpBridgeOperationEvent.operation_id)))
            chunks = set(await session.scalars(select(HttpBridgeOperationEventChunk.operation_id)))
            assert rows | chunks == expected
            for operation_id in expected:
                assert await bridge.get_operation_events(operation_id=operation_id) == [f"data: {operation_id}\n\n"]

        await assert_remaining(terminal_ids | active_ids | {"recent"})
        abandonment = await bridge.abandon_stale_operations(
            cutoff=cutoff, lease_expired_before=datetime.now(timezone.utc), batch_size=2
        )
        assert abandonment.abandonments == ()
        first = await bridge.purge_operation_spool_batch(cutoff=cutoff, batch_size=2)
        assert (first.selected_operations, first.deleted_operations) == (2, 2)
        await assert_remaining({"old-failed"} | active_ids | {"recent"})
        second = await bridge.purge_operation_spool_batch(cutoff=cutoff, batch_size=2)
        assert (second.selected_operations, second.deleted_operations) == (1, 1)
        await assert_remaining(active_ids | {"recent"})
        protected = await bridge.purge_operation_spool_batch(cutoff=cutoff, batch_size=2)
        assert (protected.selected_operations, protected.deleted_operations) == (0, 0)
        await assert_remaining(active_ids | {"recent"})

        if owner_end == "expire":
            await session.execute(
                update(HttpBridgeSessionRecord)
                .where(HttpBridgeSessionRecord.id == owner.id)
                .values(lease_expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc))
            )
            await session.commit()
        else:
            released = await bridge.release_session(
                session_id=owner.id, instance_id="single", owner_epoch=owner.owner_epoch, draining=False
            )
            assert released is not None and released.owner_instance_id is None
        stale = await bridge.purge_operation_spool_batch(cutoff=cutoff, batch_size=2)
        assert (stale.selected_operations, stale.deleted_operations) == (2, 2)
        await assert_remaining({"old-unknown", "recent"})
        last = await bridge.purge_operation_spool_batch(cutoff=cutoff, batch_size=2)
        assert (last.selected_operations, last.deleted_operations) == (1, 1)
        await assert_remaining({"recent"})


async def test_oracle_cost_backfill_bounds_eligible_rows_resumes_and_is_idempotent(oracle_runtime: AsyncEngine) -> None:
    factory = async_sessionmaker(oracle_runtime, expire_on_commit=False)
    names = (
        "before-cursor",
        "already-priced",
        "first",
        "external-source",
        "unknown-price",
        "second",
        "missing-input",
        "third",
        "external-kind",
        "missing-output",
    )
    logs = [
        RequestLog(
            request_id=name,
            requested_at=datetime(2026, 10, 24, 10),
            model="gpt-6-astra",
            status="success",
            request_kind="normal",
            input_tokens=1000,
            cached_input_tokens=500,
            output_tokens=100,
        )
        for name in names
    ]
    (
        before_cursor,
        already_priced,
        first,
        external_source,
        unknown_price,
        second,
        missing_input,
        third,
        external_kind,
        missing_output,
    ) = logs
    already_priced.cost_usd = 0.0
    external_source.model_source_id = "external"
    unknown_price.model = "unknown"
    second.model_source_kind = "subscription"
    missing_input.input_tokens = None
    third.output_tokens = None
    third.reasoning_tokens = 100
    external_kind.model_source_kind = "openai_compatible"
    missing_output.output_tokens = None
    async with factory() as session:
        session.add_all(logs)
        await session.commit()

    async with factory() as session:
        initial = await backfill_missing_costs(session, after_id=before_cursor.id, limit=2)
    assert (initial.scanned, initial.updated, initial.last_id) == (2, 1, unknown_price.id)
    async with factory() as session:
        costs = {
            name: cost
            for name, cost in (await session.execute(select(RequestLog.request_id, RequestLog.cost_usd))).all()
        }
    assert costs["first"] is not None and costs["first"] > 0
    assert costs["before-cursor"] is None
    assert costs["second"] is None and costs["third"] is None
    assert costs["already-priced"] == 0.0

    async with factory() as session:
        resumed = await backfill_missing_costs(session, after_id=initial.last_id, limit=2)
    assert (resumed.scanned, resumed.updated, resumed.last_id) == (2, 2, third.id)
    async with factory() as session:
        exhausted = await backfill_missing_costs(session, after_id=resumed.last_id, limit=2)
    assert (exhausted.scanned, exhausted.updated, exhausted.last_id) == (0, 0, third.id)
    async with factory() as session:
        repaired_costs = {
            name: cost
            for name, cost in (await session.execute(select(RequestLog.request_id, RequestLog.cost_usd))).all()
        }
        repeated = await backfill_missing_costs(session, after_id=before_cursor.id, limit=2)
    assert (repeated.scanned, repeated.updated, repeated.last_id) == (1, 0, unknown_price.id)
    async with factory() as session:
        assert {
            name: cost
            for name, cost in (await session.execute(select(RequestLog.request_id, RequestLog.cost_usd))).all()
        } == repaired_costs
        restarted = await backfill_missing_costs(session, limit=2)
    assert (restarted.scanned, restarted.updated, restarted.last_id) == (2, 1, unknown_price.id)
    async with factory() as session:
        final_costs = {
            name: cost
            for name, cost in (await session.execute(select(RequestLog.request_id, RequestLog.cost_usd))).all()
        }
    for name in ("before-cursor", "first", "second", "third"):
        assert final_costs[name] is not None and final_costs[name] > 0
    for name in ("external-source", "unknown-price", "missing-input", "external-kind", "missing-output"):
        assert final_costs[name] is None
    assert final_costs["already-priced"] == 0.0


async def test_oracle_folds_keep_an_hours_first_second_in_that_hour(oracle_runtime: AsyncEngine) -> None:
    # Production wedge: one key at 07:30 and in the first second after 08:00.
    # 08:00 is 1/3 day, so the DATE-difference epoch sat a hair below the hour
    # and the 08:00 slice re-inserted the already folded 07:00 bucket.
    from app.modules.accounts.usage_time_rollup import _fold_next_conversation_slice, _fold_next_hourly_slice
    from app.modules.reports.rollup import fold_next_report_slice

    factory = async_sessionmaker(oracle_runtime, expire_on_commit=False)
    async with factory() as session:
        session.add_all(
            RequestLog(
                request_id=f"fold-{at:%H%M%S}",
                requested_at=at,
                model="gpt-6-astra",
                status="success",
                request_kind="normal",
                conversation_id="oracle-fold-conversation",
                input_tokens=10,
                output_tokens=1,
            )
            for at in (datetime(2026, 10, 28, 7, 30), datetime(2026, 10, 28, 8, 0, 0, 400_000))
        )
        await session.commit()

    for target in (datetime(2026, 10, 28, 8), datetime(2026, 10, 28, 9)):
        async with factory() as session:
            await _fold_next_hourly_slice(session, target)
        async with factory() as session:
            await _fold_next_conversation_slice(session, target)
        async with factory() as session:
            await fold_next_report_slice(session, target)

    seven, eight = 1793170800, 1793174400
    async with factory() as session:
        for table in (RequestUsageHourlyRollup, RequestConversationHourlyRollup, RequestReportHourlyRollup):
            buckets = dict(
                (await session.execute(select(table.bucket_epoch, table.request_count).order_by(table.bucket_epoch)))
                .tuples()
                .all()
            )
            assert buckets == {seven: 1, eight: 1}, table.__tablename__
