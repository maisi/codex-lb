from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

from app.core.clients.native_egress import NativeEgressTransportError, NativeEgressWebSocket
from app.core.clients.proxy_websocket import ArchivingUpstreamWebSocket, NativeUpstreamWebSocket


async def failing_native_upstream(*, pre_dispatch: bool = True) -> tuple[ArchivingUpstreamWebSocket, AsyncMock]:
    """Use real native adapters with a closed socket or a failing command writer."""
    events: asyncio.Queue[dict[str, object] | BaseException] = asyncio.Queue()
    send_command = AsyncMock()
    native = NativeEgressWebSocket(
        status=101,
        headers=(),
        client=cast(
            Any, SimpleNamespace(_finish_request=Mock(), _send_command=send_command, _cancel_request=AsyncMock())
        ),
        process=cast(Any, None),
        request_id="closed-native-bridge",
        generation=1,
        events=events,
    )
    if pre_dispatch:
        events.put_nowait({"type": "websocket_close", "code": 1000, "reason": "closed before send"})
        await native._pump_task
    else:
        send_command.side_effect = NativeEgressTransportError(
            "native command failed after dispatch", failure_phase="websocket_send"
        )
    return (
        ArchivingUpstreamWebSocket(
            NativeUpstreamWebSocket(native),
            url="wss://upstream.invalid/responses",
            headers={},
            account_id="acc-bridge",
            archive_payloads=False,
        ),
        send_command,
    )
