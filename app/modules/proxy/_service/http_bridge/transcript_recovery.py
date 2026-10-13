"""Scoped I/O boundary for definitive, pre-submit conversation relocation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from app.core.clock import Clock, Scheduler
from app.core.openai.requests import ResponsesRequest
from app.core.utils.sse import parse_sse_data_json
from app.modules.proxy.durable_bridge_coordinator import DurableBridgeLookup, DurableBridgeSessionCoordinator
from app.modules.proxy.durable_bridge_repository import (
    DurableBridgeOperationSnapshot,
    durable_bridge_api_key_scope,
    durable_bridge_hash,
    durable_bridge_operation_id,
)
from app.modules.proxy.replay_transcript import (
    TRANSCRIPT_REPLAY_MAX_BYTES,
    TRANSCRIPT_REPLAY_MAX_TURNS,
    rebuild_transcript_input,
)

if TYPE_CHECKING:
    from app.modules.proxy._service.support import _HTTPBridgeSession, _WebSocketRequestState

logger = logging.getLogger(__name__)
_TRANSCRIPT_LOAD_TIMEOUT_SECONDS = 5.0


async def capture_settled_root(
    coordinator: DurableBridgeSessionCoordinator,
    *,
    session: _HTTPBridgeSession,
    request_state: _WebSocketRequestState,
    event_block: str,
    instance_id: str,
    scheduler: Scheduler,
) -> DurableBridgeOperationSnapshot | None:
    """Record a successful root without changing its live retry decisions."""
    if (
        request_state.operation_id is not None
        or request_state.previous_response_id is not None
        or not request_state.request_text
        or request_state.request_kind == "prewarm"
        or request_state.skip_request_log
        or session.durable_session_id is None
        or session.durable_owner_epoch is None
    ):
        return None
    event = parse_sse_data_json(event_block)
    if not isinstance(event, dict) or event.get("type") not in ("response.completed", "response.incomplete"):
        return None
    response = event.get("response")
    if (
        not isinstance(response, dict)
        or not isinstance(response.get("id"), str)
        or not isinstance(response.get("output"), list)
    ):
        return None
    # Roots are independent turns even when their bodies match. Their record
    # begins only after definitive completion, so it cannot change the existing
    # dispatch/reconnect fences or turn an ambiguous failure into a replay.
    fingerprint = durable_bridge_hash(uuid4().hex)
    try:
        return await scheduler.wait_for(
            coordinator.record_operation(
                operation_id=durable_bridge_operation_id(session.durable_session_id, fingerprint),
                session_id=session.durable_session_id,
                instance_id=instance_id,
                owner_epoch=session.durable_owner_epoch,
                request_fingerprint=fingerprint,
                api_key_scope=durable_bridge_api_key_scope(session.key.api_key_id),
                account_id=session.account.id,
                model=request_state.model,
                parent_response_id=None,
                request_text=request_state.request_text,
            ),
            timeout=_TRANSCRIPT_LOAD_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.warning("Settled bridge root unavailable for later transcript recovery", exc_info=True)
        return None


async def load_transcript_replay(
    coordinator: DurableBridgeSessionCoordinator,
    *,
    lookup: DurableBridgeLookup,
    payload: ResponsesRequest,
    anchor_response_id: str,
    deadline: float,
    scheduler: Scheduler,
    clock: Clock,
) -> ResponsesRequest | None:
    if lookup.account_id is None:
        return None
    timeout = min(_TRANSCRIPT_LOAD_TIMEOUT_SECONDS, max(0.0, deadline - clock.monotonic()))
    if timeout <= 0:
        return None
    try:
        transcript = await scheduler.wait_for(
            coordinator.get_replayable_transcript(
                response_id=anchor_response_id,
                session_id=lookup.session_id,
                account_id=lookup.account_id,
                max_turns=TRANSCRIPT_REPLAY_MAX_TURNS,
                max_bytes=TRANSCRIPT_REPLAY_MAX_BYTES,
            ),
            timeout=timeout,
        )
    except Exception:
        logger.warning("Durable transcript unavailable for pre-submit owner recovery", exc_info=True)
        return None
    if transcript is None or clock.monotonic() >= deadline:
        return None
    rebuilt = rebuild_transcript_input(
        transcript,
        payload=payload,
        anchor_response_id=anchor_response_id,
        session_id=lookup.session_id,
        account_id=lookup.account_id,
    )
    if rebuilt is None:
        return None
    return payload.model_copy(update={"input": rebuilt, "previous_response_id": None})
