from __future__ import annotations

import base64
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core.config.settings import get_settings
from app.core.openai.requests import ResponsesRequest
from app.modules.proxy.affinity import _codex_backend_identity
from app.modules.proxy.bridge_affinity_headers import (
    HTTP_BRIDGE_AFFINITY_KEY_B64_HEADER,
    HTTP_BRIDGE_AFFINITY_KEY_HEADER,
    decode_bridge_affinity_key,
)
from app.modules.proxy.http_bridge_forwarding import (
    HTTPBridgeForwardContext,
    build_owner_forward_headers,
    parse_forwarded_request,
)


@pytest.fixture(autouse=True)
def bridge_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("CODEX_LB_ENCRYPTION_KEY_FILE", str(tmp_path / "bridge.key"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize("unanchored", [False, True])
def test_generated_thread_key_survives_signed_owner_hop(unanchored: bool) -> None:
    key = _codex_backend_identity({"session-id": "process", "thread-id": "thread"}).thread_selection_key
    assert key is not None and key.startswith("\ncodex-lb-affinity-v1:")
    payload = ResponsesRequest(model="gpt-5.4", input="hi", instructions="hi")
    context = HTTPBridgeForwardContext(
        origin_instance="origin",
        target_instance="owner",
        codex_session_affinity=True,
        downstream_turn_state=None,
        original_request_unanchored=unanchored,
        original_affinity_kind="thread_header",
        original_affinity_key=key,
        signature_version="2" if unanchored else None,
    )

    headers = build_owner_forward_headers(headers={}, payload=payload, context=context)
    assert all("\n" not in value and "\r" not in value for value in headers.values())
    forwarded, error = parse_forwarded_request(headers, payload=payload, current_instance="owner")

    assert error is None
    assert forwarded is not None
    assert forwarded.context == context


def test_session_key_fallback_decodes_generated_affinity() -> None:
    from app.modules.proxy._service.http_bridge.helpers import _make_http_bridge_session_key
    from app.modules.proxy.affinity import _AffinityPolicy

    key = _codex_backend_identity({"session-id": "process", "thread-id": "thread"}).thread_selection_key
    assert key is not None
    payload = ResponsesRequest(model="gpt-5.4", input="hi", instructions="hi")
    context = HTTPBridgeForwardContext(
        origin_instance="origin",
        target_instance="owner",
        codex_session_affinity=True,
        downstream_turn_state=None,
        original_affinity_kind="thread_header",
        original_affinity_key=key,
    )
    headers = build_owner_forward_headers(headers={}, payload=payload, context=context)
    reconstructed = _make_http_bridge_session_key(
        payload,
        headers=headers,
        affinity=_AffinityPolicy(),
        api_key=None,
        request_id="req",
        allow_forwarded_affinity_headers=True,
    )
    assert reconstructed.affinity_key == key
    assert reconstructed.affinity_kind == "thread_header"
    assert reconstructed.strength == "hard"


@pytest.mark.parametrize("tamper", ["remove", "invalid", "body"])
@pytest.mark.parametrize("unanchored", [False, True])
def test_encoded_forward_requires_full_context_signature(tamper: str, unanchored: bool) -> None:
    from app.modules.proxy.http_bridge_forwarding import HTTP_BRIDGE_SIGNATURE_V2_HEADER

    key = _codex_backend_identity({"thread-id": "thread"}).thread_selection_key
    payload = ResponsesRequest(model="gpt-5.4", input="hi", instructions="hi")
    context = HTTPBridgeForwardContext(
        origin_instance="origin",
        target_instance="owner",
        codex_session_affinity=True,
        downstream_turn_state=None,
        original_request_unanchored=unanchored,
        original_affinity_kind="thread_header",
        original_affinity_key=key,
    )
    headers = build_owner_forward_headers(headers={}, payload=payload, context=context)
    if tamper == "remove":
        headers.pop(HTTP_BRIDGE_SIGNATURE_V2_HEADER)
    elif tamper == "invalid":
        headers[HTTP_BRIDGE_SIGNATURE_V2_HEADER] = "0" * 64
    else:
        payload = ResponsesRequest.model_validate({**payload.model_dump_for_forwarding(), "tools": []})
    forwarded, error = parse_forwarded_request(headers, payload=payload, current_instance="owner")
    assert forwarded is None
    assert error is not None
    assert error.payload["error"]["code"] == "bridge_forward_invalid"


@pytest.mark.parametrize("key", [" sid ", "\tsid\t", "b64:c2lk", "sid\t123", "sid", "ä-session"])
def test_literal_affinity_round_trip_preserves_identity(key: str) -> None:
    payload = ResponsesRequest(model="gpt-5.4", input="hi", instructions="hi")
    context = HTTPBridgeForwardContext(
        origin_instance="origin",
        target_instance="owner",
        codex_session_affinity=True,
        downstream_turn_state=None,
        original_affinity_kind="session_header",
        original_affinity_key=key,
    )
    headers = build_owner_forward_headers(headers={}, payload=payload, context=context)
    forwarded, error = parse_forwarded_request(headers, payload=payload, current_instance="owner")
    assert error is None
    assert forwarded is not None and forwarded.context == context
    if key == key.strip():
        assert headers[HTTP_BRIDGE_AFFINITY_KEY_HEADER] == key
        assert HTTP_BRIDGE_AFFINITY_KEY_B64_HEADER not in headers


@pytest.mark.parametrize("encoded", ["", "====", "c2l", "c2lk=", "c2lk\n", "_w==", "Zh==", "Zg", "+w=="])
def test_decoder_rejects_malformed_encoded_keys(encoded: str) -> None:
    with pytest.raises(ValueError):
        decode_bridge_affinity_key({HTTP_BRIDGE_AFFINITY_KEY_B64_HEADER: encoded})


def test_affinity_decoder_is_case_insensitive() -> None:
    key = "\ncodex-lb-affinity-v1:test"
    assert (
        decode_bridge_affinity_key(
            {HTTP_BRIDGE_AFFINITY_KEY_B64_HEADER.upper(): base64.urlsafe_b64encode(key.encode()).decode()}
        )
        == key
    )
    assert decode_bridge_affinity_key({HTTP_BRIDGE_AFFINITY_KEY_HEADER.upper(): "literal"}) == "literal"


@pytest.mark.parametrize("encoded", [False, True])
def test_affinity_decoder_rejects_duplicate_headers(encoded: bool) -> None:
    from starlette.datastructures import Headers

    name = HTTP_BRIDGE_AFFINITY_KEY_B64_HEADER if encoded else HTTP_BRIDGE_AFFINITY_KEY_HEADER
    value = "c2lk" if encoded else "sid"
    headers = Headers(raw=[(name.encode(), value.encode()), (name.encode(), value.encode())])
    with pytest.raises(ValueError):
        decode_bridge_affinity_key(headers)


@pytest.mark.parametrize("key", ["cache\x00key", "\nnot-an-internal-key", "\ncodex-lb-affinity-v1:thread_header:bad\r"])
def test_encoded_receiver_retains_logical_key_safety_checks(key: str) -> None:
    from dataclasses import replace

    from app.modules.proxy.http_bridge_forwarding import (
        HTTP_BRIDGE_SIGNATURE_V2_HEADER,
        _bridge_forward_tools_bound_signature,
    )

    payload = ResponsesRequest(model="gpt-5.4", input="hi", instructions="hi")
    context = HTTPBridgeForwardContext(
        origin_instance="origin",
        target_instance="owner",
        codex_session_affinity=True,
        downstream_turn_state=None,
        original_affinity_kind="thread_header",
        original_affinity_key="safe",
    )
    headers = build_owner_forward_headers(headers={}, payload=payload, context=context)
    del headers[HTTP_BRIDGE_AFFINITY_KEY_HEADER]
    headers[HTTP_BRIDGE_AFFINITY_KEY_B64_HEADER] = base64.urlsafe_b64encode(key.encode()).decode()
    headers[HTTP_BRIDGE_SIGNATURE_V2_HEADER] = _bridge_forward_tools_bound_signature(
        payload=payload,
        context=replace(context, original_affinity_key=key),
    )
    forwarded, error = parse_forwarded_request(headers, payload=payload, current_instance="owner")
    assert forwarded is None
    assert error is not None and error.payload["error"]["code"] == "bridge_forward_invalid"


@pytest.mark.parametrize("key", ["b64:c2lk", "\ncodex-lb-affinity-v1:test"])
def test_authenticated_session_key_is_not_decoded_twice(key: str) -> None:
    from app.modules.proxy._service.http_bridge.helpers import _forwarded_http_bridge_session_key

    result = _forwarded_http_bridge_session_key(
        {HTTP_BRIDGE_AFFINITY_KEY_B64_HEADER: "invalid!"},
        None,
        forwarded_affinity_kind="thread_header",
        forwarded_affinity_key=key,
    )
    assert result is not None and result.affinity_key == key


@pytest.mark.parametrize("encoded", [False, True])
def test_public_bridge_header_cannot_select_internal_namespace(encoded: bool) -> None:
    from app.modules.proxy._service.http_bridge.helpers import _make_http_bridge_session_key
    from app.modules.proxy.affinity import _AffinityPolicy

    key = "\ncodex-lb-affinity-v1:thread_header:known-digest"
    name = HTTP_BRIDGE_AFFINITY_KEY_B64_HEADER if encoded else HTTP_BRIDGE_AFFINITY_KEY_HEADER
    value = base64.urlsafe_b64encode(key.encode()).decode() if encoded else key
    payload = ResponsesRequest(model="gpt-5.4", input="hi", instructions="hi")
    result = _make_http_bridge_session_key(
        payload,
        headers={name: value, "x-codex-bridge-affinity-kind": "thread_header"},
        affinity=_AffinityPolicy(),
        api_key=None,
        request_id="public-request",
    )
    assert result.affinity_key == "public-request"
    assert result.affinity_kind == "request"


def test_origin_drops_spoofed_encoding_metadata() -> None:
    payload = ResponsesRequest(model="gpt-5.4", input="hi", instructions="hi")
    context = HTTPBridgeForwardContext(
        origin_instance="origin",
        target_instance="owner",
        codex_session_affinity=True,
        downstream_turn_state=None,
        original_affinity_kind="prompt_cache",
        original_affinity_key="b64:c2lk",
    )
    headers = build_owner_forward_headers(
        headers={HTTP_BRIDGE_AFFINITY_KEY_B64_HEADER.upper(): "attacker", HTTP_BRIDGE_AFFINITY_KEY_HEADER: "spoof"},
        payload=payload,
        context=context,
    )
    assert not any(name.lower() == HTTP_BRIDGE_AFFINITY_KEY_B64_HEADER for name in headers)
    assert headers[HTTP_BRIDGE_AFFINITY_KEY_HEADER] == "b64:c2lk"
    forwarded, error = parse_forwarded_request(headers, payload=payload, current_instance="owner")
    assert error is None and forwarded is not None and forwarded.context == context


@pytest.mark.parametrize("tamper", ["key", "remove", "raw", "malformed"])
@pytest.mark.parametrize("unanchored", [False, True])
def test_encoded_affinity_tampering_is_rejected(tamper: str, unanchored: bool) -> None:
    payload = ResponsesRequest(model="gpt-5.4", input="hi", instructions="hi")
    key = _codex_backend_identity({"thread-id": "thread"}).thread_selection_key
    context = HTTPBridgeForwardContext(
        origin_instance="origin",
        target_instance="owner",
        codex_session_affinity=True,
        downstream_turn_state=None,
        original_request_unanchored=unanchored,
        original_affinity_kind="thread_header",
        original_affinity_key=key,
    )
    headers = build_owner_forward_headers(headers={}, payload=payload, context=context)
    if tamper == "key":
        other = _codex_backend_identity({"thread-id": "other"}).thread_selection_key
        assert other is not None
        headers[HTTP_BRIDGE_AFFINITY_KEY_B64_HEADER] = base64.urlsafe_b64encode(other.encode()).decode()
    elif tamper == "remove":
        del headers[HTTP_BRIDGE_AFFINITY_KEY_B64_HEADER]
    elif tamper == "raw":
        headers[HTTP_BRIDGE_AFFINITY_KEY_HEADER] = "spoof"
    else:
        headers[HTTP_BRIDGE_AFFINITY_KEY_B64_HEADER] = "invalid!"
    forwarded, error = parse_forwarded_request(headers, payload=payload, current_instance="owner")
    assert forwarded is None
    assert error is not None and error.payload["error"]["code"] == "bridge_forward_invalid"
