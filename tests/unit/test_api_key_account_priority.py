"""Per-API-key account priority: a strict waterfall over the eligible pool.

The ranks come from an API key's ordered account assignments. They order the
pool; they never widen or restrict it, and they never override recovery
admission or hard eligibility filtering.
"""

from __future__ import annotations

from app.core.balancer import (
    HEALTH_TIER_HEALTHY,
    HEALTH_TIER_PROBING,
    ROUTING_POLICY_PRESERVE,
    AccountState,
    select_account,
)
from app.db.models import AccountStatus

PRIORITY = {"first": 0, "second": 1}


def _pick(states, priority=PRIORITY, **kwargs):
    result = select_account(states, routing_strategy="usage_weighted", account_priority=priority, **kwargs)
    assert result.account is not None
    return result.account.account_id


def test_top_rank_wins_even_when_far_more_used():
    """Strict waterfall: rank beats the usage-balancing that would pick 'second'."""
    states = [
        AccountState("first", AccountStatus.ACTIVE, used_percent=92.0),
        AccountState("second", AccountStatus.ACTIVE, used_percent=3.0),
    ]
    assert _pick(states) == "first"


def test_without_priority_usage_still_decides():
    """Regression guard: no ranks means the pre-existing behavior is untouched."""
    states = [
        AccountState("first", AccountStatus.ACTIVE, used_percent=92.0),
        AccountState("second", AccountStatus.ACTIVE, used_percent=3.0),
    ]
    assert _pick(states, priority=None) == "second"


def test_failover_when_top_rank_leaves_the_eligible_pool():
    """Failover is free: an ineligible account is simply not in `available`."""
    states = [
        AccountState("first", AccountStatus.PAUSED, used_percent=1.0),
        AccountState("second", AccountStatus.ACTIVE, used_percent=80.0),
    ]
    assert _pick(states) == "second"


def test_priority_outranks_preserve_policy():
    """Decision: a key's explicit order wins over account-level preserve."""
    states = [
        AccountState("first", AccountStatus.ACTIVE, used_percent=70.0, routing_policy=ROUTING_POLICY_PRESERVE),
        AccountState("second", AccountStatus.ACTIVE, used_percent=5.0),
    ]
    assert _pick(states) == "first"


def test_unranked_account_is_a_last_resort_not_a_restriction():
    """Priority orders the pool; it does not shrink it."""
    ranked_available = [
        AccountState("first", AccountStatus.ACTIVE, used_percent=90.0),
        AccountState("unlisted", AccountStatus.ACTIVE, used_percent=0.0),
    ]
    assert _pick(ranked_available) == "first"

    ranked_gone = [
        AccountState("first", AccountStatus.PAUSED, used_percent=0.0),
        AccountState("unlisted", AccountStatus.ACTIVE, used_percent=90.0),
    ]
    assert _pick(ranked_gone) == "unlisted"


def test_lower_rank_beats_unranked():
    states = [
        AccountState("second", AccountStatus.ACTIVE, used_percent=88.0),
        AccountState("unlisted", AccountStatus.ACTIVE, used_percent=1.0),
    ]
    assert _pick(states) == "second"


def test_priority_applies_to_drain_strategies():
    """The early-return drain strategies honor rank too, not just the sorted path."""
    states = [
        AccountState("second", AccountStatus.ACTIVE, used_percent=10.0),
        AccountState("first", AccountStatus.ACTIVE, used_percent=10.0),
    ]
    result = select_account(states, routing_strategy="sequential_drain", account_priority=PRIORITY)
    assert result.account is not None
    assert result.account.account_id == "first"


def test_recovery_admission_still_outranks_priority():
    """A due recovery probe is a liveness admission and must not be starved."""
    states = [
        AccountState("first", AccountStatus.ACTIVE, used_percent=10.0, health_tier=HEALTH_TIER_HEALTHY),
        AccountState(
            "second",
            AccountStatus.ACTIVE,
            used_percent=10.0,
            health_tier=HEALTH_TIER_PROBING,
            last_selected_at=None,
        ),
    ]
    assert _pick(states) == "second"
