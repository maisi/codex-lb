from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core import usage as usage_core
from app.core.balancer import (
    HEALTH_TIER_DRAINING,
    HEALTH_TIER_HEALTHY,
    QUOTA_EXCEEDED_COOLDOWN_SECONDS,
    RATE_LIMITED_MIN_COOLDOWN_SECONDS,
    ROUTING_POLICY_PRESERVE,
    AccountState,
    evaluate_health_tier,
)
from app.core.balancer import (
    ROUTING_POLICY_BURN_FIRST as ROUTING_POLICY_BURN_FIRST,
)
from app.core.balancer.logic import plausible_rate_limit_reset_at
from app.core.config import settings as config_settings
from app.core.config.settings import get_settings
from app.core.resilience.toggles import resolve_resilience_toggles
from app.core.usage.quota import apply_usage_quota
from app.db.models import Account, AccountStatus, AdditionalUsageHistory, UsageHistory
from app.modules.proxy._load_balancer.error_rate import error_rate_weight_multiplier
from app.modules.proxy._load_balancer.types import (
    RuntimeState,
)
from app.modules.usage.mappers import usage_history_to_window_row


def _state_from_account(
    *,
    account: Account,
    primary_entry: UsageHistory | AdditionalUsageHistory | None,
    secondary_entry: UsageHistory | AdditionalUsageHistory | None,
    runtime: RuntimeState,
    access_token_expires_at: float | None = None,
    now: float,
    soft_drain_enabled: bool | None = None,
) -> AccountState:
    routing_policy = _normalize_account_routing_policy(getattr(account, "routing_policy", None))
    normalized_usage = _normalize_usage_inputs(
        account=account,
        primary_entry=primary_entry,
        secondary_entry=secondary_entry,
        now_epoch=int(now),
    )
    primary_used = normalized_usage.primary_used
    primary_reset = normalized_usage.primary_reset
    primary_window_minutes = normalized_usage.primary_window_minutes
    effective_secondary_entry = normalized_usage.effective_secondary_entry
    secondary_used = normalized_usage.secondary_used
    secondary_reset = normalized_usage.secondary_reset
    effective_blocked_at = float(account.blocked_at) if account.blocked_at is not None else runtime.blocked_at
    credits_has, credits_unlimited, credits_balance = _extract_credit_status(
        primary_entry,
        effective_secondary_entry,
        secondary_entry,
        recorded_after=effective_blocked_at if account.status == AccountStatus.QUOTA_EXCEEDED else None,
    )

    # If the usage window has reset (reset_at is in the past), the last
    # recorded sample describes an expired window at ANY used percentage:
    # upstream may have stopped reporting the window entirely (e.g. the
    # temporary 5h-limit removal), in which case the row is never rewritten
    # and a frozen sub-100% sample would otherwise hold drain tiers and
    # budget pressure forever. Zero the derived locals — not the stored
    # rows — so the account is not incorrectly blocked or deprioritised
    # while waiting for the next usage refresh. Expired samples map to 0.0
    # rather than None because usage-derived status recovery only evaluates
    # non-None percentages.
    if primary_used is not None and primary_reset is not None and primary_reset <= int(now):
        primary_used = 0.0
        primary_reset = None
    # A strictly newer long-window row proves a later fetch no longer
    # reported the short window: drop the stale duration — whether or not
    # the stale row's reset has elapsed — so phase planning stops treating
    # the account as having a short phase window.
    if (
        primary_window_minutes is not None
        and primary_entry is not None
        and effective_secondary_entry is not None
        and effective_secondary_entry is not primary_entry
        and (effective_secondary_entry.recorded_at - primary_entry.recorded_at).total_seconds()
        > _SIBLING_FETCH_MARGIN_SECONDS
    ):
        primary_window_minutes = None
    if secondary_used is not None and secondary_reset is not None and secondary_reset <= int(now):
        secondary_used = 0.0
        secondary_reset = None
    ignore_zero_capacity_primary_runtime_reset = False
    status_seed = account.status
    long_window_quota_available = _usage_entry_is_recent_available(effective_secondary_entry, now=now)
    # Preserve actual 429 cooldowns (marked by blocked_at) before zero-primary
    # recovery can rewrite status from fresh long-window usage.
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
            # Only the replica that observed this block may recover before its persisted deadline.
            early_freshness_entry = _rate_limited_freshness_entry(
                account=account,
                primary_entry=primary_entry,
                long_window_entry=effective_secondary_entry,
                now=now,
            )
            if _usage_entry_recorded_after_block(early_freshness_entry, effective_blocked_at):
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
        primary_used = _health_tier_primary_used(
            plan_type=account.plan_type,
            primary_used=primary_used,
        )
        primary_reset = None
        primary_window_minutes = None
        ignore_zero_capacity_primary_runtime_reset = account.status == AccountStatus.RATE_LIMITED
        if account.status == AccountStatus.RATE_LIMITED:
            status_seed = AccountStatus.ACTIVE

    # Use account.reset_at from DB as the authoritative source for runtime reset
    # and to survive process restarts.
    persisted_reset_at = float(account.reset_at) if account.reset_at is not None else None
    runtime_reset_at = runtime.reset_at
    # Validate only future RATE_LIMITED hints. Elapsed deadlines must still
    # reach apply_usage_quota's ordinary expiry transition, and QUOTA_EXCEEDED
    # deadlines have separate recovery semantics.
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

    # Resetless rate limits retain a minimum hold after blocked_at across restarts;
    # after this floor, recovery uses the normal compare-and-set persistence path.
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
        and effective_runtime_reset > now
        and effective_blocked_at is None
        and effective_secondary_entry is not None
        and long_window_quota_available
        and effective_secondary_entry.reset_at is not None
        and float(effective_secondary_entry.reset_at) > effective_runtime_reset
    ):
        effective_runtime_reset = None

    # Post-block evidence clears resets after debounce. Quota recovery uses persisted
    # markers; early rate-limit recovery requires this replica's runtime block evidence.
    cooldown_ready = False
    if account.status == AccountStatus.QUOTA_EXCEEDED:
        cooldown_ready = (
            effective_blocked_at is not None and now >= effective_blocked_at + QUOTA_EXCEEDED_COOLDOWN_SECONDS
        )
    elif (
        runtime.cooldown_until is not None
        and runtime.cooldown_until <= now
        and runtime.blocked_at is not None
        and effective_blocked_at is not None
        and runtime.blocked_at >= effective_blocked_at
    ):
        cooldown_ready = True

    if cooldown_ready and effective_blocked_at is not None:
        if account.status == AccountStatus.QUOTA_EXCEEDED:
            freshness_entry = (
                effective_secondary_entry if secondary_used is not None and secondary_used < 100.0 else None
            )
        elif account.status == AccountStatus.RATE_LIMITED:
            freshness_entry = _rate_limited_freshness_entry(
                account=account,
                primary_entry=primary_entry,
                long_window_entry=effective_secondary_entry,
                now=now,
            )
        else:
            freshness_entry = None
        if _usage_entry_recorded_after_block(freshness_entry, effective_blocked_at):
            effective_runtime_reset = None

    rejected_reset_recovery_evidence = False
    if rejected_persisted_rate_limit_reset:
        rejected_reset_freshness_entry = _rate_limited_freshness_entry(
            account=account,
            primary_entry=primary_entry,
            long_window_entry=effective_secondary_entry,
            now=now,
        )
        # Recovery requires actual evidence without exhaustion in any applicable window.
        all_quota_windows_available = (
            (primary_used is None or float(primary_used) < 100.0)
            and (secondary_used is None or float(secondary_used) < 100.0)
            and (primary_used is not None or secondary_used is not None)
        )
        rejected_reset_recovery_evidence = all_quota_windows_available and _usage_entry_is_recent_available(
            rejected_reset_freshness_entry, now=now
        )
        if effective_blocked_at is not None:
            # A sample predating the 429 cannot disprove the persisted block.
            rejected_reset_recovery_evidence = (
                rejected_reset_recovery_evidence
                and now >= effective_blocked_at + RATE_LIMITED_MIN_COOLDOWN_SECONDS
                and _usage_entry_recorded_after_block(rejected_reset_freshness_entry, effective_blocked_at)
            )

    # A resetless rate limit whose runtime cooldown was lost (e.g. a restart
    # after a 429 without reset metadata) has no deadline to expire and no
    # post-block evidence trail; a long-window sample alone must not clear
    # it. Evidence-gated clearing above always starts from a persisted or
    # runtime reset, so this only matches the truly resetless case.
    resetless_rate_limit_without_evidence = (
        status_seed == AccountStatus.RATE_LIMITED and account.reset_at is None and runtime.reset_at is None
    )

    quota_secondary_used = secondary_used
    if (
        status_seed == AccountStatus.QUOTA_EXCEEDED
        and secondary_used is not None
        and secondary_used >= 100.0
        and effective_secondary_entry is not None
        and (
            not _usage_entry_is_recent_enough(effective_secondary_entry.recorded_at, now=now)
            or (
                effective_blocked_at is not None
                and not _usage_entry_recorded_after_block(effective_secondary_entry, effective_blocked_at)
            )
        )
    ):
        # Historical exhaustion cannot rewrite a newer upstream rejection's deadline.
        quota_secondary_used = None

    status, used_percent, reset_at = apply_usage_quota(
        status=status_seed,
        primary_used=primary_used,
        primary_reset=primary_reset,
        primary_window_minutes=primary_window_minutes,
        runtime_reset=effective_runtime_reset,
        secondary_used=quota_secondary_used,
        secondary_reset=secondary_reset,
        credits_has=credits_has,
        credits_unlimited=credits_unlimited,
        credits_balance=credits_balance,
        infer_status_from_usage=False,
        now=now,
    )
    if resetless_rate_limit_without_evidence and primary_used is None and status == AccountStatus.ACTIVE:
        status = AccountStatus.RATE_LIMITED
    if rejected_persisted_rate_limit_reset and not rejected_reset_recovery_evidence:
        status = AccountStatus.RATE_LIMITED
        reset_at = float(account.reset_at)

    next_blocked_at = (
        effective_blocked_at
        if status == AccountStatus.QUOTA_EXCEEDED
        or (status == AccountStatus.RATE_LIMITED and account.status != AccountStatus.QUOTA_EXCEEDED)
        else None
    )

    settings = get_settings()
    if soft_drain_enabled is None:
        # C2-3 resilience toggles: callers on the request path pass the
        # dashboard value; anything else inherits the env alias / default.
        soft_drain_enabled = resolve_resilience_toggles(None, startup_settings=settings).soft_drain_enabled
    new_tier = _sync_runtime_health_tier(
        account_id=account.id,
        status=status,
        used_percent=used_percent,
        secondary_used_percent=secondary_used,
        routing_policy=routing_policy,
        runtime=runtime,
        now=now,
        soft_drain_enabled=soft_drain_enabled,
    )

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
    usage_exhaustion_evidence_status = status in (AccountStatus.QUOTA_EXCEEDED, AccountStatus.RATE_LIMITED)

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
        priority_used_percent=used_percent if usage_exhaustion_evidence_status else None,
        priority_secondary_used_percent=secondary_used if usage_exhaustion_evidence_status else None,
        access_token_expires_at=access_token_expires_at,
        inflight_response_creates=runtime.inflight_response_creates,
        inflight_streams=runtime.inflight_streams,
        leased_tokens=runtime.leased_tokens,
        routing_policy=routing_policy,
        selection_weight_multiplier=error_rate_weight_multiplier(runtime, now),
    )


def _extract_credit_status(
    *entries: _UsageWindowEntry | None,
    recorded_after: float | None = None,
) -> tuple[bool | None, bool | None, float | None]:
    credit_entries: list[UsageHistory] = [
        entry
        for entry in entries
        if isinstance(entry, UsageHistory)
        and (recorded_after is None or _usage_entry_recorded_after_block(entry, recorded_after))
        and not (entry.credits_has is None and entry.credits_unlimited is None and entry.credits_balance is None)
    ]
    if not credit_entries:
        return None, None, None
    entry = max(
        credit_entries,
        key=lambda item: item.recorded_at if item.recorded_at is not None else datetime.min,
    )
    if entry is not None:
        return entry.credits_has, entry.credits_unlimited, entry.credits_balance
    return None, None, None


def _normalize_account_routing_policy(value: str | None) -> str:
    if value in _ACCOUNT_ROUTING_POLICIES:
        return value
    return _ROUTING_POLICY_NORMAL


@dataclass(frozen=True, slots=True)
class _NormalizedUsageInputs:
    primary_used: float | None
    primary_reset: int | None
    primary_window_minutes: int | None
    effective_secondary_entry: _UsageWindowEntry | None
    secondary_used: float | None
    secondary_reset: int | None


def _normalize_usage_inputs(
    *,
    account: Account,
    primary_entry: _UsageWindowEntry | None,
    secondary_entry: _UsageWindowEntry | None,
    now_epoch: int,
) -> _NormalizedUsageInputs:
    """Normalize persisted usage for routing and explicit probe settlement."""
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
    # Weekly-only accounts may not emit a dedicated secondary row; treat the
    # weekly primary row as quota-window input for balancer decisions. When
    # both rows exist, prefer the newer weekly snapshot.
    if primary_row is not None and usage_core.should_use_weekly_primary(primary_row, secondary_row):
        effective_secondary_entry = primary_entry
        primary_used = None
        primary_reset = None
        primary_window_minutes = None

    secondary_used = effective_secondary_entry.used_percent if effective_secondary_entry else None
    secondary_reset = effective_secondary_entry.reset_at if effective_secondary_entry else None

    # Expired rows describe prior windows. Zero derived values without
    # rewriting history so stale samples cannot hold drain tiers forever.
    if primary_used is not None and primary_reset is not None and primary_reset <= now_epoch:
        primary_used = 0.0
        primary_reset = None
    # A strictly newer long-window row proves a later fetch no longer
    # reported the short window, so phase planning drops the stale duration.
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

    return _NormalizedUsageInputs(
        primary_used=primary_used,
        primary_reset=primary_reset,
        primary_window_minutes=primary_window_minutes,
        effective_secondary_entry=effective_secondary_entry,
        secondary_used=secondary_used,
        secondary_reset=secondary_reset,
    )


def _health_tier_primary_used(*, plan_type: str | None, primary_used: float | None) -> float | None:
    """Drop primary usage when the plan has no primary-window capacity."""
    # Storage may retain a legacy/synthetic primary row for free accounts. The
    # health state machine must follow plan capacity, not the row's slot, or
    # both ordinary routing and Force Probe can drain an account on a quota it
    # does not have.
    if usage_core.capacity_for_plan(plan_type, "primary") == 0.0:
        return None
    return primary_used


def _sync_runtime_health_tier(
    *,
    account_id: str,
    status: AccountStatus,
    used_percent: float | None,
    secondary_used_percent: float | None,
    routing_policy: str,
    runtime: RuntimeState,
    now: float,
    soft_drain_enabled: bool,
) -> int:
    before = (
        runtime.health_tier,
        runtime.drain_entered_at,
        runtime.probe_success_streak,
    )
    if soft_drain_enabled:
        new_tier = evaluate_health_tier(
            AccountState(
                account_id=account_id,
                status=status,
                used_percent=used_percent,
                secondary_used_percent=secondary_used_percent,
                last_error_at=runtime.last_error_at,
                error_count=runtime.error_count,
                health_tier=runtime.health_tier,
                routing_policy=routing_policy,
            ),
            now=now,
            drain_entered_at=runtime.drain_entered_at,
            probe_success_streak=runtime.probe_success_streak,
            # Drain/probe thresholds are fixed in
            # ``app/core/balancer/logic.py`` (evaluate_health_tier defaults).
        )
        if new_tier == HEALTH_TIER_DRAINING and runtime.health_tier != HEALTH_TIER_DRAINING:
            runtime.drain_entered_at = now
            runtime.probe_success_streak = 0
        if new_tier == HEALTH_TIER_HEALTHY:
            runtime.drain_entered_at = None
            runtime.probe_success_streak = 0
        runtime.health_tier = new_tier
    else:
        runtime.health_tier = HEALTH_TIER_HEALTHY
        runtime.drain_entered_at = None
        runtime.probe_success_streak = 0

    after = (
        runtime.health_tier,
        runtime.drain_entered_at,
        runtime.probe_success_streak,
    )
    if after != before:
        runtime.version += 1
        runtime.health_version += 1
    return runtime.health_tier


def _rate_limited_freshness_entry(
    *,
    account: Account,
    primary_entry: _UsageWindowEntry | None,
    long_window_entry: _UsageWindowEntry | None,
    now: float,
) -> _UsageWindowEntry | None:
    if (
        long_window_entry is not None
        and long_window_entry.reset_at is not None
        and long_window_entry.reset_at <= int(now)
    ):
        long_window_entry = None
    if (
        long_window_entry is not None
        and long_window_entry.window == "monthly"
        and usage_core.capacity_for_plan(account.plan_type, "monthly") is None
    ):
        long_window_entry = None
    # Freshness cannot prove recovery while an applicable long window is
    # still exhausted, even if the primary sample reports available quota.
    if long_window_entry is not None and not (
        long_window_entry.used_percent is not None and float(long_window_entry.used_percent) < 100.0
    ):
        return None
    if long_window_entry is not None and long_window_entry.window == "monthly":
        return long_window_entry
    if primary_entry is None:
        return long_window_entry
    # A newer long-window row can replace primary evidence only after the
    # primary reset expires. Otherwise the primary sample must itself
    # report available quota.
    primary_window_expired = primary_entry.reset_at is not None and float(primary_entry.reset_at) <= now
    if (
        primary_window_expired
        and long_window_entry is not None
        and long_window_entry.recorded_at > primary_entry.recorded_at
    ):
        return long_window_entry
    if primary_entry.used_percent is not None and float(primary_entry.used_percent) < 100.0:
        return primary_entry
    return None


def _usage_entry_is_recent_available(entry: _UsageWindowEntry | None, *, now: float) -> bool:
    return (
        entry is not None
        and _usage_entry_is_recent_enough(entry.recorded_at, now=now)
        and entry.used_percent is not None
        and float(entry.used_percent) < 100.0
    )


def _usage_entry_recorded_after_block(entry: _UsageWindowEntry | None, blocked_at: float) -> bool:
    if entry is None or entry.recorded_at is None:
        return False
    recorded_at = entry.recorded_at
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)
    # Persistence truncates block timestamps to whole seconds. A sample
    # within that same second cannot prove it was captured after the block.
    return int(recorded_at.timestamp()) > int(blocked_at)


def _usage_entry_is_recent_enough(recorded_at: datetime | None, *, now: float) -> bool:
    if recorded_at is None:
        return False
    current_time = datetime.fromtimestamp(now, tz=timezone.utc)
    interval_seconds = max(_usage_refresh_interval_seconds() * 2, 180)
    recorded_time = recorded_at if recorded_at.tzinfo is not None else recorded_at.replace(tzinfo=timezone.utc)
    return recorded_time >= current_time - timedelta(seconds=interval_seconds)


def _usage_refresh_interval_seconds() -> int:
    return config_settings.get_settings().usage_refresh_interval_seconds


_SIBLING_FETCH_MARGIN_SECONDS = 5.0
_UsageWindowEntry = UsageHistory | AdditionalUsageHistory
_ROUTING_POLICY_NORMAL = "normal"
_ACCOUNT_ROUTING_POLICIES = frozenset({_ROUTING_POLICY_NORMAL, ROUTING_POLICY_BURN_FIRST, ROUTING_POLICY_PRESERVE})
