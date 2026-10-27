"""Routing traces explain a selection without influencing it."""

from __future__ import annotations

import json
import logging
import time

import pytest

from app.core.balancer import HEALTH_TIER_DRAINING, ROUTING_POLICY_BURN_FIRST, AccountState
from app.db.models import AccountStatus
from app.modules.proxy import routing_trace
from app.modules.proxy._load_balancer.sticky_selection import _select_account_preferring_budget_safe

pytestmark = pytest.mark.unit

TIERS = {"acct1": 0, "acct2": 0, "acct3": 1}


def _pool(*, acct2_used: float = 10.0) -> list[AccountState]:
    now = time.time()
    return [
        AccountState(
            "acct1",
            AccountStatus.RATE_LIMITED,
            used_percent=100.0,
            reset_at=int(now + 3600),
            routing_policy=ROUTING_POLICY_BURN_FIRST,
        ),
        AccountState("acct2", AccountStatus.ACTIVE, used_percent=acct2_used),
        AccountState("acct3", AccountStatus.ACTIVE, used_percent=10.0, routing_policy=ROUTING_POLICY_BURN_FIRST),
    ]


def _select(states: list[AccountState]):
    return _select_account_preferring_budget_safe(
        states,
        prefer_earlier_reset=False,
        routing_strategy="capacity_weighted",
        budget_threshold_pct=95.0,
        account_priority=TIERS,
    )


def _trace(
    draft,
    *,
    selected: str | None,
    request_id: str = "req-1",
    attempt: int = 1,
    required_account_id: str | None = None,
    excluded_account_ids: frozenset[str] = frozenset(),
):
    return routing_trace.build_trace(
        draft,
        request_id=request_id,
        attempt=attempt,
        api_key_id="key-1",
        model="gpt-test",
        routing_strategy="capacity_weighted",
        sticky_kind="prompt_cache",
        account_priority=TIERS,
        budget_threshold_pct=95.0,
        excluded_account_ids=excluded_account_ids,
        required_account_id=required_account_id,
        selected_account_id=selected,
        error_code=None,
    )


def test_trace_explains_a_tier_failover_inside_the_real_selector():
    states = _pool()
    with routing_trace.capture() as draft:
        routing_trace.note_pool(states, states, now=time.time())
        result = _select(states)

    assert result.account is not None and result.account.account_id == "acct2"
    trace = _trace(draft, selected="acct2")
    assert trace.outcome == "new_selection"
    assert trace.serving_rank == 0
    assert trace.decided_by == "within_budget"
    by_id = {candidate.account_id: candidate for candidate in trace.candidates}
    assert by_id["acct1"].eligible is False
    assert by_id["acct1"].unavailable_reason == "rate_limited"
    assert by_id["acct1"].rank == 0
    assert by_id["acct2"].eligible is True
    assert by_id["acct3"].rank == 1
    assert by_id["acct3"].routing_policy == ROUTING_POLICY_BURN_FIRST


def test_trace_shows_the_threshold_moving_traffic_to_the_next_tier():
    states = _pool(acct2_used=97.0)
    with routing_trace.capture() as draft:
        routing_trace.note_pool(states, states, now=time.time())
        result = _select(states)

    assert result.account is not None and result.account.account_id == "acct3"
    trace = _trace(draft, selected="acct3")
    assert trace.serving_rank == 1
    assert trace.decided_by == "burn_first"
    assert {c.account_id: c.over_budget_threshold for c in trace.candidates}["acct2"] is True


def test_capped_and_unhealthy_accounts_are_labelled():
    now = time.time()
    states = [
        AccountState("acct1", AccountStatus.ACTIVE, used_percent=5.0, cooldown_until=now + 300),
        AccountState("acct2", AccountStatus.ACTIVE, used_percent=5.0, health_tier=HEALTH_TIER_DRAINING),
        AccountState("acct3", AccountStatus.ACTIVE, used_percent=5.0),
    ]
    with routing_trace.capture() as draft:
        routing_trace.note_pool(states, [states[1]], now=now, overloaded_account_ids=["acct2"])

    by_id = {candidate.account_id: candidate for candidate in _trace(draft, selected="acct2").candidates}
    assert by_id["acct1"].unavailable_reason == "cooldown"
    assert by_id["acct2"].health == "draining"
    assert by_id["acct2"].overload_backoff is True
    assert by_id["acct2"].eligible is True
    assert by_id["acct3"].unavailable_reason == "concurrency_cap"


def test_hard_sticky_narrowing_is_not_reported_as_a_cap():
    now = time.time()
    states = [AccountState("acct1", AccountStatus.ACTIVE), AccountState("acct2", AccountStatus.ACTIVE)]
    with routing_trace.capture() as draft:
        routing_trace.note_pool(states, [states[0]], now=now, sticky_owner_account_id="acct1", hard_sticky=True)

    trace = _trace(draft, selected="acct1")
    assert trace.outcome == "kept_owner"
    assert trace.serving_rank is None
    assert {c.account_id: c.unavailable_reason for c in trace.candidates}["acct2"] == "not_continuity_owner"


@pytest.mark.parametrize(
    ("owner", "required", "selected", "expected"),
    [
        (None, None, "acct2", "new_selection"),
        ("acct1", None, "acct1", "kept_owner"),
        ("acct1", None, "acct2", "moved_from_owner"),
        (None, "acct2", "acct2", "required_account"),
        ("acct1", None, None, "no_account"),
    ],
)
def test_outcome_classification(owner, required, selected, expected):
    states = _pool()
    with routing_trace.capture() as draft:
        routing_trace.note_pool(states, states, now=time.time(), sticky_owner_account_id=owner)

    assert _trace(draft, selected=selected, required_account_id=required).outcome == expected


def test_ranked_accounts_missing_from_the_pool_are_listed_without_retry_exclusions():
    states = [AccountState("acct2", AccountStatus.ACTIVE)]
    with routing_trace.capture() as draft:
        routing_trace.note_pool(states, states, now=time.time())

    trace = _trace(draft, selected="acct2", excluded_account_ids=frozenset({"acct1"}))
    assert trace.ranked_accounts_not_offered == ("acct3",)
    assert trace.excluded_account_ids == ("acct1",)


def test_notes_outside_a_capture_are_ignored():
    states = _pool()
    routing_trace.note_pool(states, states, now=time.time())
    routing_trace.note_serving_rank(3)
    routing_trace.note_decided_by("burn_first")
    assert _select(states).account is not None


def test_store_keeps_attempts_in_order_and_evicts_the_oldest_request():
    store = routing_trace.RoutingTraceStore(max_requests=2)
    states = _pool()
    with routing_trace.capture() as draft:
        routing_trace.note_pool(states, states, now=time.time())
    for request_id in ("a", "a", "b", "c"):
        store.add(_trace(draft, selected="acct2", request_id=request_id, attempt=store.next_attempt(request_id)))

    assert store.get("a") == []
    assert [trace.attempt for trace in store.get("b")] == [1]
    assert store.next_attempt("c") == 2


def test_log_line_redacts_account_ids_when_privacy_requires(caplog):
    states = _pool()
    with routing_trace.capture() as draft:
        routing_trace.note_pool(states, states, now=time.time(), sticky_owner_account_id="acct1")
    trace = _trace(draft, selected="acct2", request_id="req-redact")
    routing_trace.get_routing_trace_store().clear()

    with caplog.at_level(logging.INFO, logger=routing_trace.__name__):
        routing_trace.record_selection(trace, redact_account_ids=True)

    line = next(record.getMessage() for record in caplog.records if "req-redact" in record.getMessage())
    payload = json.loads(line.split("trace=", 1)[1])
    assert payload["selected_account_id"] == "<redacted>"
    assert payload["sticky_owner_account_id"] == "<redacted>"
    assert {candidate["account_id"] for candidate in payload["candidates"]} == {"<redacted>"}
    assert "acct" not in line.split("trace=", 1)[1]
    assert routing_trace.get_routing_trace_store().get("req-redact") == [trace]
