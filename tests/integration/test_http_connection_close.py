"""Readiness probes must receive EOF when any Connection token requests close."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
import uvicorn

from app.cli import _load_http_protocol_class
from app.core.http_protocol import UpgradeTolerantH11Protocol

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(params=["httptools", "h11"])
async def readiness_server(request: pytest.FixtureRequest, app_instance) -> AsyncIterator[int]:
    protocol = _load_http_protocol_class() if request.param == "httptools" else UpgradeTolerantH11Protocol
    server = uvicorn.Server(uvicorn.Config(app_instance, host="127.0.0.1", port=0, http=protocol, log_level="warning"))
    task = asyncio.create_task(server.serve())
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    await task
                    pytest.fail("Readiness server exited before startup")
                await asyncio.sleep(0.01)
        yield server.servers[0].sockets[0].getsockname()[1]
    finally:
        server.should_exit = True
        try:
            async with asyncio.timeout(15):
                await task
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


async def _read_readiness(reader: asyncio.StreamReader) -> bytes:
    async with asyncio.timeout(3):
        headers = await reader.readuntil(b"\r\n\r\n")
        assert headers.startswith(b"HTTP/1.1 200 OK\r\n"), headers
        length = next(
            int(line.split(b":", 1)[1]) for line in headers.lower().splitlines() if line.startswith(b"content-length:")
        )
        body = json.loads(await reader.readexactly(length))
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"
    return headers


@pytest.mark.parametrize(
    "value",
    [b"close", b"Close", b"CLOSE", b"keep-alive, Close", b"Close\r\nConnection: keep-alive"],
    ids=["lower", "oci", "upper", "tokens", "repeated"],
)
async def test_readiness_connection_close_sends_complete_response_then_eof(readiness_server: int, value: bytes) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", readiness_server)
    try:
        writer.write(b"GET /health/ready HTTP/1.1\r\nHost: 10.0.0.31:2455\r\nConnection: " + value + b"\r\n\r\n")
        await writer.drain()
        headers = await _read_readiness(reader)
        async with asyncio.timeout(2):
            assert await reader.read(1) == b""
        assert b"connection: close\r\n" in headers.lower()
    finally:
        writer.close()
        await writer.wait_closed()


async def test_readiness_keepalive_serves_second_request(readiness_server: int) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", readiness_server)
    try:
        for _ in range(2):
            writer.write(b"GET /health/ready HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
            await writer.drain()
            headers = await _read_readiness(reader)
            assert b"connection: close\r\n" not in headers.lower()
    finally:
        writer.close()
        await writer.wait_closed()


async def test_declined_upgrade_retains_close_token(readiness_server: int) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", readiness_server)
    try:
        writer.write(
            b"GET /health/ready HTTP/1.1\r\nHost: 127.0.0.1\r\n"
            b"Connection: Upgrade, HTTP2-Settings, Close\r\nUpgrade: h2c\r\n"
            b"HTTP2-Settings: AAMAAABkAARAAAAAAAIAAAAA\r\n\r\n"
        )
        await writer.drain()
        headers = await _read_readiness(reader)
        async with asyncio.timeout(2):
            assert await reader.read(1) == b""
        assert b"connection: close\r\n" in headers.lower()
    finally:
        writer.close()
        await writer.wait_closed()
