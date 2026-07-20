from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Literal

from app.core import usage as usage_core
from app.core.balancer import (
    HEALTH_TIER_DRAINING,
    HEALTH_TIER_HEALTHY,
    QUOTA_EXCEEDED_COOLDOWN_SECONDS,
    RATE_LIMITED_MIN_COOLDOWN_SECONDS,
    ROUTING_POLICY_BURN_FIRST,
    ROUTING_POLICY_PRESERVE,
    AccountState,
    evaluate_health_tier,
    plausible_rate_limit_reset_at,
)
from app.core.usage.quota import apply_usage_quota
from app.db.models import Account, AccountStatus, AdditionalUsageHistory, UsageHistory
from app.modules.usage.mappers import usage_history_to_window_row

_SIBLING_FETCH_MARGIN_SECONDS = 5.0
_ROUTING_POLICY_NORMAL = "normal"
_ACCOUNT_ROUTING_POLICIES = frozenset({_ROUTING_POLICY_NORMAL, ROUTING_POLICY_BURN_FIRST, ROUTING_POLICY_PRESERVE})
_ADDITIONAL_QUOTA_ROUTING_POLICIES = _ACCOUNT_ROUTING_POLICIES | frozenset({"inherit"})

_UsageWindowEntry = UsageHistory | AdditionalUsageHistory
AccountLeaseKind = Literal["response_create", "stream"]


@dataclass
class RuntimeState:
    reset_at: float | None = None
    cooldown_until: float | None = None
    last_error_at: float | None = None
    last_selected_at: float | None = None
    error_count: int = 0
    version: int = 0
    blocked_at: float | None = None
    health_tier: int = 0
    drain_entered_at: float | None = None
    probe_success_streak: int = 0
    inflight_response_creates: int = 0
    inflight_streams: int = 0
    leased_tokens: float = 0.0
    leases: dict[str, AccountLease] | None = None


@dataclass(frozen=True, slots=True)
class AccountLease:
    lease_id: str
    account_id: str
    kind: AccountLeaseKind
    acquired_at: float
    estimated_tokens: float = 0.0


@dataclass(frozen=True, slots=True)
class AccountStateDependencies:
    time: Callable[[], float]
    utcnow: Callable[[], datetime]
    settings: object
    usage_refresh_interval_seconds: int


def normalize_account_routing_policy(value: str | None) -> str:
    if value in _ACCOUNT_ROUTING_POLICIES:
        return value
    return _ROUTING_POLICY_NORMAL


def state_from_account(
    *,
    account: Account,
    primary_entry: UsageHistory | AdditionalUsageHistory | None,
    secondary_entry: UsageHistory | AdditionalUsageHistory | None,
    runtime: RuntimeState,
    dependencies: AccountStateDependencies,
) -> AccountState:
    routing_policy = normalize_account_routing_policy(getattr(account, "routing_policy", None))
    primary_used = primary_entry.used_percent if primary_entry else None
    primary_reset = primary_entry.reset_at if primary_entry else None
    primary_window_minutes = primary_entry.window_minutes if primary_entry else None
    effective_secondary_entry = secondary_entry
    if (
        effective_secondary_entry is not None
        and effective_secondary_entry.window == "monthly"
        and usage_core.capacity_for_plan(account.plan_type, "monthly") is None
    ):
        effective_secondary_entry = None
    primary_row = usage_history_to_window_row(primary_entry) if primary_entry is not None else None
    secondary_row = usage_history_to_window_row(secondary_entry) if secondary_entry is not None else None
    # Weekly-only accounts may not emit a dedicated secondary row. When both
    # rows exist, prefer the newer weekly snapshot.
    if primary_row is not None and usage_core.should_use_weekly_primary(primary_row, secondary_row):
        effective_secondary_entry = primary_entry
        primary_used = None
        primary_reset = None
        primary_window_minutes = None

    secondary_used = effective_secondary_entry.used_percent if effective_secondary_entry else None
    secondary_reset = effective_secondary_entry.reset_at if effective_secondary_entry else None
    credits_has, credits_unlimited, credits_balance = extract_credit_status(
        primary_entry,
        effective_secondary_entry,
        secondary_entry,
    )

    now = dependencies.time()
    now_epoch = int(now)
    if primary_used is not None and primary_reset is not None and primary_reset <= now_epoch:
        primary_used = 0.0
        primary_reset = None
    if (
        primary_window_minutes is not None
        and primary_entry is not None
        and effective_secondary_entry is not None
        and effective_secondary_entry is not primary_entry
        and (effective_secondary_entry.recorded_at - primary_entry.recorded_at).total_seconds()
        > _SIBLING_FETCH_MARGIN_SECONDS
    ):
        primary_window_minutes = None
    if secondary_used is not None and secondary_reset is not None and secondary_reset <= now_epoch:
        secondary_used = 0.0
        secondary_reset = None

    ignore_zero_capacity_primary_runtime_reset = False
    status_seed = account.status
    long_window_quota_available = (
        effective_secondary_entry is not None
        and usage_entry_is_recent_enough(effective_secondary_entry.recorded_at, dependencies=dependencies)
        and effective_secondary_entry.used_percent is not None
        and float(effective_secondary_entry.used_percent) < 100.0
    )
    effective_blocked_at = float(account.blocked_at) if account.blocked_at is not None else runtime.blocked_at

    rate_limited_cooldown_deadline: float | None = None
    if account.status == AccountStatus.RATE_LIMITED and effective_blocked_at is not None:
        persisted_deadline = plausible_rate_limit_reset_at(account.reset_at, now=now) or (
            effective_blocked_at + RATE_LIMITED_MIN_COOLDOWN_SECONDS
        )
        if now < persisted_deadline:
            rate_limited_cooldown_deadline = persisted_deadline
        if (
            rate_limited_cooldown_deadline is not None
            and runtime.cooldown_until is not None
            and runtime.cooldown_until <= now
            and runtime.blocked_at is not None
            and runtime.blocked_at >= effective_blocked_at
        ):
            early_freshness_entry = rate_limited_freshness_entry(
                account=account,
                primary_entry=primary_entry,
                long_window_entry=effective_secondary_entry,
                now=dependencies.time(),
            )
            if early_freshness_entry is not None and early_freshness_entry.recorded_at is not None:
                recorded_epoch = early_freshness_entry.recorded_at.replace(tzinfo=timezone.utc).timestamp()
                if recorded_epoch > effective_blocked_at:
                    rate_limited_cooldown_deadline = None

    if usage_core.capacity_for_plan(account.plan_type, "primary") == 0.0 and (
        account.status != AccountStatus.RATE_LIMITED
        or (
            rate_limited_cooldown_deadline is None
            and (
                (
                    primary_window_minutes is not None
                    and not usage_core.is_primary_window_minutes(primary_window_minutes)
                    and long_window_quota_available
                )
                or (primary_entry is None and long_window_quota_available)
            )
        )
    ):
        primary_used = None
        primary_reset = None
        primary_window_minutes = None
        ignore_zero_capacity_primary_runtime_reset = account.status == AccountStatus.RATE_LIMITED
        if account.status == AccountStatus.RATE_LIMITED:
            status_seed = AccountStatus.ACTIVE

    persisted_reset_at = float(account.reset_at) if account.reset_at is not None else None
    runtime_reset_at = runtime.reset_at
    if account.status == AccountStatus.RATE_LIMITED:
        if persisted_reset_at is not None and persisted_reset_at > now:
            persisted_reset_at = plausible_rate_limit_reset_at(persisted_reset_at, now=now)
        if runtime_reset_at is not None and runtime_reset_at > now:
            runtime_reset_at = plausible_rate_limit_reset_at(runtime_reset_at, now=now)
    rejected_persisted_rate_limit_reset = (
        account.status == AccountStatus.RATE_LIMITED
        and account.reset_at is not None
        and persisted_reset_at is None
        and account.reset_at > now
    )
    db_reset_at = None if ignore_zero_capacity_primary_runtime_reset else persisted_reset_at
    if status_seed in (AccountStatus.RATE_LIMITED, AccountStatus.QUOTA_EXCEEDED) or runtime.blocked_at is not None:
        effective_runtime_reset = db_reset_at or runtime_reset_at
    else:
        effective_runtime_reset = None

    if (
        status_seed == AccountStatus.RATE_LIMITED
        and effective_runtime_reset is None
        and effective_blocked_at is not None
    ):
        floor_deadline = effective_blocked_at + RATE_LIMITED_MIN_COOLDOWN_SECONDS
        if now < floor_deadline:
            effective_runtime_reset = floor_deadline

    if (
        account.status == AccountStatus.QUOTA_EXCEEDED
        and effective_runtime_reset is not None
        and effective_runtime_reset > dependencies.time()
        and effective_blocked_at is None
        and effective_secondary_entry is not None
        and usage_entry_is_recent_enough(effective_secondary_entry.recorded_at, dependencies=dependencies)
        and effective_secondary_entry.used_percent is not None
        and float(effective_secondary_entry.used_percent) < 100.0
        and effective_secondary_entry.reset_at is not None
        and float(effective_secondary_entry.reset_at) > effective_runtime_reset
    ):
        effective_runtime_reset = None

    cooldown_ready = False
    if account.status == AccountStatus.QUOTA_EXCEEDED:
        cooldown_ready = (
            effective_blocked_at is not None
            and dependencies.time() >= effective_blocked_at + QUOTA_EXCEEDED_COOLDOWN_SECONDS
        )
    elif (
        runtime.cooldown_until is not None
        and runtime.cooldown_until <= dependencies.time()
        and runtime.blocked_at is not None
        and effective_blocked_at is not None
        and runtime.blocked_at >= effective_blocked_at
    ):
        cooldown_ready = True

    if cooldown_ready and effective_blocked_at is not None:
        if account.status == AccountStatus.QUOTA_EXCEEDED:
            freshness_entry = effective_secondary_entry
        elif account.status == AccountStatus.RATE_LIMITED:
            freshness_entry = rate_limited_freshness_entry(
                account=account,
                primary_entry=primary_entry,
                long_window_entry=effective_secondary_entry,
                now=dependencies.time(),
            )
        else:
            freshness_entry = None
        if freshness_entry and freshness_entry.recorded_at is not None:
            recorded_epoch = freshness_entry.recorded_at.replace(tzinfo=timezone.utc).timestamp()
            if recorded_epoch > effective_blocked_at:
                effective_runtime_reset = None

    rejected_reset_recovery_evidence = False
    if rejected_persisted_rate_limit_reset:
        rejected_reset_freshness_entry = rate_limited_freshness_entry(
            account=account,
            primary_entry=primary_entry,
            long_window_entry=effective_secondary_entry,
            now=dependencies.time(),
        )
        all_quota_windows_available = (
            (primary_used is None or float(primary_used) < 100.0)
            and (secondary_used is None or float(secondary_used) < 100.0)
            and (primary_used is not None or secondary_used is not None)
        )
        rejected_reset_recovery_evidence = all_quota_windows_available and usage_entry_is_recent_available(
            rejected_reset_freshness_entry,
            dependencies=dependencies,
        )
        if effective_blocked_at is not None:
            rejected_reset_recovery_evidence = (
                rejected_reset_recovery_evidence
                and now >= effective_blocked_at + RATE_LIMITED_MIN_COOLDOWN_SECONDS
                and usage_entry_recorded_after_block(rejected_reset_freshness_entry, effective_blocked_at)
            )

    resetless_rate_limit_without_evidence = (
        status_seed == AccountStatus.RATE_LIMITED and account.reset_at is None and runtime.reset_at is None
    )

    status, used_percent, reset_at = apply_usage_quota(
        status=status_seed,
        primary_used=primary_used,
        primary_reset=primary_reset,
        primary_window_minutes=primary_window_minutes,
        runtime_reset=effective_runtime_reset,
        secondary_used=secondary_used,
        secondary_reset=secondary_reset,
        credits_has=credits_has,
        credits_unlimited=credits_unlimited,
        credits_balance=credits_balance,
        infer_status_from_usage=False,
    )
    if resetless_rate_limit_without_evidence and primary_used is None and status == AccountStatus.ACTIVE:
        status = AccountStatus.RATE_LIMITED
    if rejected_persisted_rate_limit_reset and not rejected_reset_recovery_evidence:
        status = AccountStatus.RATE_LIMITED
        reset_at = float(account.reset_at)

    if status == AccountStatus.QUOTA_EXCEEDED:
        next_blocked_at = effective_blocked_at
    elif status == AccountStatus.RATE_LIMITED and account.status != AccountStatus.QUOTA_EXCEEDED:
        next_blocked_at = effective_blocked_at
    else:
        next_blocked_at = None

    settings = dependencies.settings
    if getattr(settings, "soft_drain_enabled", True):
        new_tier = evaluate_health_tier(
            AccountState(
                account_id=account.id,
                status=status,
                used_percent=used_percent,
                secondary_used_percent=secondary_used,
                last_error_at=runtime.last_error_at,
                error_count=runtime.error_count,
                health_tier=runtime.health_tier,
                routing_policy=routing_policy,
            ),
            now=dependencies.time(),
            drain_entered_at=runtime.drain_entered_at,
            probe_success_streak=runtime.probe_success_streak,
        )
        if new_tier == HEALTH_TIER_DRAINING and runtime.health_tier != HEALTH_TIER_DRAINING:
            runtime.drain_entered_at = dependencies.time()
            runtime.probe_success_streak = 0
        if new_tier == HEALTH_TIER_HEALTHY:
            runtime.drain_entered_at = None
            runtime.probe_success_streak = 0
        runtime.health_tier = new_tier
    else:
        new_tier = HEALTH_TIER_HEALTHY
        runtime.drain_entered_at = None
        runtime.probe_success_streak = 0
        runtime.health_tier = HEALTH_TIER_HEALTHY

    inflight_pressure_pct = (runtime.inflight_response_creates + runtime.inflight_streams) * getattr(
        settings, "proxy_account_inflight_penalty_pct", 2.5
    )
    leased_token_pressure_pct = 0.0
    long_window_key = "secondary"
    if effective_secondary_entry is not None and effective_secondary_entry.window == "monthly":
        long_window_key = "monthly"
    capacity_credits = usage_core.capacity_for_plan(account.plan_type, long_window_key) or 0.0
    if capacity_credits > 0.0 and runtime.leased_tokens > 0:
        lease_token_weight = getattr(settings, "proxy_account_lease_token_weight", 1.0)
        leased_token_pressure_pct = runtime.leased_tokens * lease_token_weight / capacity_credits * 100.0
    pressure_pct = inflight_pressure_pct + leased_token_pressure_pct
    effective_used_percent = None if used_percent is None else min(100.0, used_percent + pressure_pct)
    effective_secondary_used_percent = None if secondary_used is None else min(100.0, secondary_used + pressure_pct)

    return AccountState(
        account_id=account.id,
        status=status,
        used_percent=effective_used_percent,
        reset_at=reset_at,
        primary_reset_at=primary_reset,
        primary_window_minutes=primary_window_minutes,
        blocked_at=next_blocked_at,
        cooldown_until=runtime.cooldown_until,
        secondary_used_percent=effective_secondary_used_percent,
        secondary_reset_at=secondary_reset,
        last_error_at=runtime.last_error_at,
        last_selected_at=runtime.last_selected_at,
        error_count=runtime.error_count,
        deactivation_reason=account.deactivation_reason,
        plan_type=account.plan_type,
        capacity_credits=capacity_credits,
        health_tier=new_tier,
        inflight_response_creates=runtime.inflight_response_creates,
        inflight_streams=runtime.inflight_streams,
        leased_tokens=runtime.leased_tokens,
        routing_policy=routing_policy,
    )


def background_recovery_state_from_account(
    *,
    account: Account,
    primary_entry: UsageHistory | None,
    secondary_entry: UsageHistory | None,
    dependencies: AccountStateDependencies,
) -> AccountState:
    """Evaluate recovery for a persisted blocked account without live runtime state."""
    runtime = RuntimeState()
    blocked_at = float(account.blocked_at) if account.blocked_at is not None else None
    now = dependencies.time()
    reset_at = float(account.reset_at) if account.reset_at is not None else None
    valid_reset_at = plausible_rate_limit_reset_at(reset_at, now=now)

    if blocked_at is not None:
        runtime.blocked_at = blocked_at
    if account.status == AccountStatus.RATE_LIMITED and blocked_at is not None and valid_reset_at is not None:
        runtime.cooldown_until = valid_reset_at
    state = state_from_account(
        account=account,
        primary_entry=primary_entry,
        secondary_entry=secondary_entry,
        runtime=runtime,
        dependencies=dependencies,
    )
    if account.status == AccountStatus.RATE_LIMITED:
        freshness_entry = rate_limited_freshness_entry(
            account=account,
            primary_entry=primary_entry,
            long_window_entry=secondary_entry,
            now=dependencies.time(),
        )
        if blocked_at is not None and reset_at is not None and reset_at <= now:
            minimum_floor_deadline = blocked_at + RATE_LIMITED_MIN_COOLDOWN_SECONDS
            if now < minimum_floor_deadline or not usage_entry_recorded_after_block(freshness_entry, blocked_at):
                return replace(
                    state,
                    status=AccountStatus.RATE_LIMITED,
                    reset_at=reset_at,
                    blocked_at=blocked_at,
                    cooldown_until=max(reset_at, minimum_floor_deadline),
                )
        elif blocked_at is None and reset_at is not None and reset_at <= now:
            if not usage_entry_is_recent_available(freshness_entry, dependencies=dependencies):
                return replace(
                    state,
                    status=AccountStatus.RATE_LIMITED,
                    reset_at=reset_at,
                    blocked_at=None,
                    cooldown_until=None,
                )
        if reset_at is None:
            return replace(
                state,
                status=AccountStatus.RATE_LIMITED,
                reset_at=None,
                blocked_at=blocked_at,
                cooldown_until=None,
            )
    return state


def select_long_window_entry(
    *,
    account: Account,
    monthly_entry: UsageHistory | None,
    secondary_entry: UsageHistory | AdditionalUsageHistory | None,
) -> UsageHistory | AdditionalUsageHistory | None:
    if monthly_entry is not None and usage_core.capacity_for_plan(account.plan_type, "monthly") is not None:
        return monthly_entry
    return secondary_entry


def rate_limited_freshness_entry(
    *,
    account: Account,
    primary_entry: _UsageWindowEntry | None,
    long_window_entry: _UsageWindowEntry | None,
    now: float,
) -> _UsageWindowEntry | None:
    if (
        long_window_entry is not None
        and long_window_entry.window == "monthly"
        and usage_core.capacity_for_plan(account.plan_type, "monthly") is not None
    ):
        return long_window_entry
    if primary_entry is None:
        return long_window_entry
    if long_window_entry is None:
        return primary_entry
    primary_window_expired = primary_entry.reset_at is not None and float(primary_entry.reset_at) <= now
    long_window_available = long_window_entry.used_percent is not None and float(long_window_entry.used_percent) < 100.0
    if primary_window_expired and long_window_available and long_window_entry.recorded_at > primary_entry.recorded_at:
        return long_window_entry
    return primary_entry


def usage_entry_is_recent_available(
    entry: _UsageWindowEntry | None,
    *,
    dependencies: AccountStateDependencies,
) -> bool:
    return (
        entry is not None
        and usage_entry_is_recent_enough(entry.recorded_at, dependencies=dependencies)
        and entry.used_percent is not None
        and float(entry.used_percent) < 100.0
    )


def usage_entry_recorded_after_block(entry: _UsageWindowEntry | None, blocked_at: float) -> bool:
    if entry is None or entry.recorded_at is None:
        return False
    recorded_at = entry.recorded_at
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)
    return recorded_at.timestamp() > blocked_at


def extract_credit_status(
    *entries: _UsageWindowEntry | None,
) -> tuple[bool | None, bool | None, float | None]:
    credit_entries: list[UsageHistory] = [
        entry
        for entry in entries
        if isinstance(entry, UsageHistory)
        and not (entry.credits_has is None and entry.credits_unlimited is None and entry.credits_balance is None)
    ]
    if not credit_entries:
        return None, None, None
    entry = max(
        credit_entries,
        key=lambda item: item.recorded_at if item.recorded_at is not None else datetime.min,
    )
    return entry.credits_has, entry.credits_unlimited, entry.credits_balance


def usage_entry_is_recent_enough(
    recorded_at: datetime | None,
    *,
    dependencies: AccountStateDependencies,
) -> bool:
    if recorded_at is None:
        return False
    current_time = dependencies.utcnow()
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    interval_seconds = max(dependencies.usage_refresh_interval_seconds * 2, 180)
    recorded_time = recorded_at if recorded_at.tzinfo is not None else recorded_at.replace(tzinfo=timezone.utc)
    return recorded_time >= current_time - timedelta(seconds=interval_seconds)
