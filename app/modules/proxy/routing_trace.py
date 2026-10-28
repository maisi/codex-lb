"""Per-request explanation of the proxy's account choice.

Selection runs deep inside the load balancer, across sticky, unbound, tier and
budget passes. Rather than threading a result object through every branch,
``LoadBalancer.select_account`` opens a draft for the current selection
(a ContextVar) and the selection paths leave notes on it. The draft then becomes
a ``RoutingTrace``: logged as one line and kept in a bounded in-memory store
keyed by request id, which the dashboard's request details read.

Traces are diagnostics, not records: the store is per process and forgets the
oldest requests first, and nothing here influences which account is chosen.
"""

from __future__ import annotations

import json
import logging
from collections import OrderedDict
from collections.abc import Collection, Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from typing import Literal

from app.core.balancer import (
    ERROR_BACKOFF_THRESHOLD,
    HEALTH_TIER_DRAINING,
    HEALTH_TIER_PROBING,
    AccountState,
    select_account,
)
from app.db.models import AccountStatus

logger = logging.getLogger(__name__)

RoutingOutcome = Literal["kept_owner", "moved_from_owner", "new_selection", "required_account", "no_account"]

MAX_TRACED_REQUESTS = 2000
MAX_ATTEMPTS_PER_REQUEST = 10


@dataclass(slots=True)
class _Draft:
    states: list[AccountState] = field(default_factory=list)
    selectable_account_ids: frozenset[str] = frozenset()
    overloaded_account_ids: frozenset[str] = frozenset()
    sticky_owner_account_id: str | None = None
    hard_sticky: bool = False
    owner_flags: dict[str, bool] = field(default_factory=dict)
    serving_rank: int | None = None
    serving_rank_noted: bool = False
    decided_by: str | None = None
    now: float = 0.0


_ACTIVE: ContextVar[_Draft | None] = ContextVar("routing_trace_draft", default=None)


@dataclass(frozen=True, slots=True)
class RoutingCandidate:
    account_id: str
    rank: int | None
    routing_policy: str
    status: str
    health: str
    primary_used_percent: float | None
    secondary_used_percent: float | None
    over_budget_threshold: bool
    eligible: bool
    overload_backoff: bool
    unavailable_reason: str | None


@dataclass(frozen=True, slots=True)
class RoutingTrace:
    request_id: str
    attempt: int
    recorded_at: datetime
    api_key_id: str | None
    model: str | None
    routing_strategy: str
    sticky_kind: str | None
    sticky_owner_account_id: str | None
    outcome: RoutingOutcome
    selected_account_id: str | None
    serving_rank: int | None
    decided_by: str | None
    owner_flags: dict[str, bool]
    budget_threshold_pct: float
    key_ranks_accounts: bool
    excluded_account_ids: tuple[str, ...]
    ranked_accounts_not_offered: tuple[str, ...]
    candidates: tuple[RoutingCandidate, ...]
    error_code: str | None


@contextmanager
def capture() -> Iterator[_Draft]:
    """Collect notes for one selection; nested selections get their own draft."""
    draft = _Draft()
    token = _ACTIVE.set(draft)
    try:
        yield draft
    finally:
        _ACTIVE.reset(token)


def note_pool(
    states: Iterable[AccountState],
    selectable: Iterable[AccountState],
    *,
    now: float,
    sticky_owner_account_id: str | None = None,
    hard_sticky: bool = False,
    overloaded_account_ids: Collection[str] = (),
) -> None:
    """Record the candidate pool; a selection that retries keeps the last pool."""
    draft = _ACTIVE.get()
    if draft is None:
        return
    # Copies: selection resets elapsed rate limits on the live objects, and the
    # trace must show the state the decision was made on.
    draft.states = [replace(state) for state in states]
    draft.selectable_account_ids = frozenset(state.account_id for state in selectable)
    draft.overloaded_account_ids = frozenset(overloaded_account_ids)
    draft.sticky_owner_account_id = sticky_owner_account_id
    draft.hard_sticky = hard_sticky
    draft.owner_flags = {}
    draft.serving_rank = None
    draft.serving_rank_noted = False
    draft.decided_by = None
    draft.now = now


def note_owner_flags(**flags: bool) -> None:
    """Why a sticky owner was kept or left (budget pressure, reallocation, ...)."""
    draft = _ACTIVE.get()
    if draft is not None:
        draft.owner_flags = dict(flags)


def note_serving_rank(rank: int | None) -> None:
    draft = _ACTIVE.get()
    if draft is not None:
        draft.serving_rank = rank
        draft.serving_rank_noted = True


def note_decided_by(pass_name: str) -> None:
    """The budget-safe selector pass that returned; the last pass to run wins."""
    draft = _ACTIVE.get()
    if draft is not None:
        draft.decided_by = pass_name


def build_trace(
    draft: _Draft,
    *,
    request_id: str,
    attempt: int,
    api_key_id: str | None,
    model: str | None,
    routing_strategy: str,
    sticky_kind: str | None,
    account_priority: Mapping[str, int] | None,
    budget_threshold_pct: float,
    excluded_account_ids: Collection[str],
    required_account_id: str | None,
    selected_account_id: str | None,
    error_code: str | None,
) -> RoutingTrace:
    ranks = dict(account_priority or {})
    # ``now`` is the selection's own clock reading; without a noted pool there
    # are no candidates to evaluate against it.
    now = draft.now
    candidates = tuple(
        _candidate(state, draft=draft, rank=ranks.get(state.account_id), threshold=budget_threshold_pct, now=now)
        for state in draft.states
    )
    offered = {state.account_id for state in draft.states}
    outcome = _outcome(
        selected_account_id=selected_account_id,
        sticky_owner_account_id=draft.sticky_owner_account_id,
        required_account_id=required_account_id,
    )
    serving_rank = None
    if outcome not in ("kept_owner", "required_account", "no_account") and ranks:
        serving_rank = draft.serving_rank if draft.serving_rank_noted else ranks.get(selected_account_id or "")
    return RoutingTrace(
        request_id=request_id,
        attempt=attempt,
        recorded_at=datetime.now(timezone.utc),
        api_key_id=api_key_id,
        model=model,
        routing_strategy=routing_strategy,
        sticky_kind=sticky_kind,
        sticky_owner_account_id=draft.sticky_owner_account_id,
        outcome=outcome,
        selected_account_id=selected_account_id,
        serving_rank=serving_rank,
        decided_by=None if outcome in ("kept_owner", "no_account") else draft.decided_by,
        owner_flags=dict(draft.owner_flags),
        budget_threshold_pct=budget_threshold_pct,
        key_ranks_accounts=bool(ranks),
        excluded_account_ids=tuple(sorted(excluded_account_ids)),
        ranked_accounts_not_offered=tuple(
            account_id
            for account_id, _ in sorted(ranks.items(), key=lambda item: item[1])
            if account_id not in offered and account_id not in excluded_account_ids
        ),
        candidates=candidates,
        error_code=error_code,
    )


def _outcome(
    *,
    selected_account_id: str | None,
    sticky_owner_account_id: str | None,
    required_account_id: str | None,
) -> RoutingOutcome:
    if selected_account_id is None:
        return "no_account"
    if required_account_id is not None and selected_account_id == required_account_id:
        return "required_account"
    if sticky_owner_account_id is None:
        return "new_selection"
    if selected_account_id == sticky_owner_account_id:
        return "kept_owner"
    return "moved_from_owner"


def _candidate(
    state: AccountState,
    *,
    draft: _Draft,
    rank: int | None,
    threshold: float,
    now: float,
) -> RoutingCandidate:
    primary = state.priority_used_percent if state.priority_used_percent is not None else state.used_percent
    secondary = (
        state.priority_secondary_used_percent
        if state.priority_secondary_used_percent is not None
        else state.secondary_used_percent
    )
    reason = _unavailable_reason(state, draft=draft, now=now)
    return RoutingCandidate(
        account_id=state.account_id,
        rank=rank,
        routing_policy=state.routing_policy,
        status=_status_value(state.status),
        health=_health_name(state.health_tier),
        primary_used_percent=primary,
        secondary_used_percent=secondary,
        over_budget_threshold=primary is not None and primary > threshold,
        eligible=reason is None,
        overload_backoff=state.account_id in draft.overloaded_account_ids,
        unavailable_reason=reason,
    )


def _unavailable_reason(state: AccountState, *, draft: _Draft, now: float) -> str | None:
    # The single-account strategy applies exactly the hard eligibility filters
    # (status, reset windows, cooldown, error backoff) and nothing pool-relative.
    probe = select_account(
        [replace(state)],
        now=now,
        routing_strategy="single_account",
        allow_backoff_fallback=False,
        allow_usage_exhaustion_error=False,
    )
    if probe.account is not None:
        if state.account_id in draft.selectable_account_ids:
            return None
        return "not_continuity_owner" if draft.hard_sticky else "concurrency_cap"
    status = _status_value(state.status)
    if status != AccountStatus.ACTIVE.value:
        return status
    if state.cooldown_until is not None and state.cooldown_until > now:
        return "cooldown"
    if state.error_count >= ERROR_BACKOFF_THRESHOLD:
        return "error_backoff"
    return "unavailable"


def _status_value(status: AccountStatus | str) -> str:
    return status.value if isinstance(status, AccountStatus) else str(status)


def _health_name(tier: int) -> str:
    if tier == HEALTH_TIER_DRAINING:
        return "draining"
    if tier == HEALTH_TIER_PROBING:
        return "probing"
    return "healthy"


class RoutingTraceStore:
    """Most recent traces per request id, oldest requests evicted first."""

    def __init__(self, max_requests: int = MAX_TRACED_REQUESTS) -> None:
        self._max_requests = max_requests
        self._traces: OrderedDict[str, list[RoutingTrace]] = OrderedDict()

    def next_attempt(self, request_id: str) -> int:
        return len(self._traces.get(request_id, ())) + 1

    def add(self, trace: RoutingTrace) -> None:
        attempts = self._traces.setdefault(trace.request_id, [])
        attempts.append(trace)
        del attempts[:-MAX_ATTEMPTS_PER_REQUEST]
        self._traces.move_to_end(trace.request_id)
        while len(self._traces) > self._max_requests:
            self._traces.popitem(last=False)

    def get(self, request_id: str) -> list[RoutingTrace]:
        return list(self._traces.get(request_id, ()))

    def clear(self) -> None:
        self._traces.clear()


_STORE = RoutingTraceStore()


def get_routing_trace_store() -> RoutingTraceStore:
    return _STORE


def record_selection(trace: RoutingTrace, *, redact_account_ids: bool) -> None:
    _STORE.add(trace)
    logger.info(
        "Proxy account selection trace request_id=%s trace=%s",
        trace.request_id,
        json.dumps(_log_payload(trace, redact_account_ids=redact_account_ids), separators=(",", ":")),
    )


def _log_payload(trace: RoutingTrace, *, redact_account_ids: bool) -> dict[str, object]:
    def account(account_id: str | None) -> str | None:
        if account_id is None or not redact_account_ids:
            return account_id
        return "<redacted>"

    payload = asdict(trace)
    payload.pop("request_id")
    payload["recorded_at"] = trace.recorded_at.isoformat()
    payload["sticky_owner_account_id"] = account(trace.sticky_owner_account_id)
    payload["selected_account_id"] = account(trace.selected_account_id)
    payload["excluded_account_ids"] = [account(value) for value in trace.excluded_account_ids]
    payload["ranked_accounts_not_offered"] = [account(value) for value in trace.ranked_accounts_not_offered]
    for candidate in payload["candidates"]:
        candidate["account_id"] = account(candidate["account_id"])
    return payload
