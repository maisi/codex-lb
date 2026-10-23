"""Per-API-key account priority: a strict waterfall over the eligible pool.

The ranks come from an API key's ordered account assignments. They order the
pool; they never widen or restrict it, and they never override recovery
admission or hard eligibility filtering.
"""

from __future__ import annotations

import time

import pytest

from app.core.balancer import (
    HEALTH_TIER_HEALTHY,
    HEALTH_TIER_PROBING,
    ROUTING_POLICY_BURN_FIRST,
    ROUTING_POLICY_PRESERVE,
    AccountState,
    select_account,
)
from app.db.models import AccountStatus
from app.modules.proxy._load_balancer.sticky_selection import _select_account_preferring_budget_safe

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


# ---------------------------------------------------------------------------
# The proxy path: the budget-safe selector every fresh pick goes through.
#
# It runs burn-first and budget passes over pre-filtered subsets before
# ``select_account`` sees the pool, so rank has to be settled ahead of them or a
# lower-ranked burn_first / non-preserve account wins outright.
# ---------------------------------------------------------------------------

_PROXY_STRATEGIES = (
    "capacity_weighted",
    "usage_weighted",
    "round_robin",
    "relative_availability",
    "fill_first",
    "sequential_drain",
)


def _pick_proxy_path(states, priority=PRIORITY, *, routing_strategy="capacity_weighted", **kwargs):
    result = _select_account_preferring_budget_safe(
        states,
        prefer_earlier_reset=False,
        routing_strategy=routing_strategy,
        budget_threshold_pct=95.0,
        account_priority=priority,
        **kwargs,
    )
    assert result.account is not None
    return result.account.account_id


@pytest.mark.parametrize("routing_strategy", _PROXY_STRATEGIES)
def test_proxy_path_lower_ranked_burn_first_does_not_jump_the_queue(routing_strategy):
    states = [
        AccountState("first", AccountStatus.ACTIVE, used_percent=10.0),
        AccountState("second", AccountStatus.ACTIVE, used_percent=10.0, routing_policy=ROUTING_POLICY_BURN_FIRST),
    ]
    assert _pick_proxy_path(states, routing_strategy=routing_strategy) == "first"


@pytest.mark.parametrize("routing_strategy", _PROXY_STRATEGIES)
def test_proxy_path_top_ranked_preserve_still_serves(routing_strategy):
    states = [
        AccountState("first", AccountStatus.ACTIVE, used_percent=70.0, routing_policy=ROUTING_POLICY_PRESERVE),
        AccountState("second", AccountStatus.ACTIVE, used_percent=5.0),
    ]
    assert _pick_proxy_path(states, routing_strategy=routing_strategy) == "first"


def test_proxy_path_budget_threshold_moves_traffic_down_one_rank():
    """Decision: crossing the budget threshold is the trigger to fail over."""
    states = [
        AccountState("first", AccountStatus.ACTIVE, used_percent=96.0),
        AccountState("second", AccountStatus.ACTIVE, used_percent=10.0),
    ]
    assert _pick_proxy_path(states) == "second"


def test_proxy_path_next_rank_takes_over_even_when_it_is_preserve():
    """Rank outranks preserve on the way down too, not only at the top."""
    states = [
        AccountState("first", AccountStatus.ACTIVE, used_percent=96.0),
        AccountState("second", AccountStatus.ACTIVE, used_percent=10.0, routing_policy=ROUTING_POLICY_PRESERVE),
    ]
    assert _pick_proxy_path(states) == "second"


def test_proxy_path_rank_order_returns_once_every_rank_is_over_budget():
    states = [
        AccountState("first", AccountStatus.ACTIVE, used_percent=97.0),
        AccountState("second", AccountStatus.ACTIVE, used_percent=96.0, routing_policy=ROUTING_POLICY_BURN_FIRST),
    ]
    assert _pick_proxy_path(states) == "first"


def test_proxy_path_fails_over_when_top_rank_is_cooling_down():
    states = [
        AccountState("first", AccountStatus.ACTIVE, used_percent=1.0, cooldown_until=time.time() + 600),
        AccountState("second", AccountStatus.ACTIVE, used_percent=50.0),
    ]
    assert _pick_proxy_path(states) == "second"


def test_proxy_path_routing_policy_still_orders_within_a_tier():
    """Unranked accounts share the last tier, where burn_first keeps its pull."""
    states = [
        AccountState("first", AccountStatus.PAUSED, used_percent=1.0),
        AccountState("unlisted-normal", AccountStatus.ACTIVE, used_percent=1.0),
        AccountState(
            "unlisted-burn", AccountStatus.ACTIVE, used_percent=60.0, routing_policy=ROUTING_POLICY_BURN_FIRST
        ),
    ]
    assert _pick_proxy_path(states) == "unlisted-burn"


def test_proxy_path_recovery_admission_still_outranks_priority():
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
    assert _pick_proxy_path(states) == "second"


def test_proxy_path_without_priority_burn_first_still_wins():
    """Regression guard: unranked keys keep the burn-first preference."""
    states = [
        AccountState("first", AccountStatus.ACTIVE, used_percent=10.0),
        AccountState("second", AccountStatus.ACTIVE, used_percent=10.0, routing_policy=ROUTING_POLICY_BURN_FIRST),
    ]
    assert _pick_proxy_path(states, priority=None) == "second"


def test_proxy_path_strategy_balances_inside_a_shared_rank():
    """Accounts sharing a rank compete on usage; the next rank still waits."""
    tiers = {"first": 0, "second": 0, "third": 1}
    states = [
        AccountState("first", AccountStatus.ACTIVE, used_percent=80.0),
        AccountState("second", AccountStatus.ACTIVE, used_percent=5.0),
        AccountState("third", AccountStatus.ACTIVE, used_percent=0.0),
    ]
    assert _pick_proxy_path(states, tiers, routing_strategy="usage_weighted") == "second"
