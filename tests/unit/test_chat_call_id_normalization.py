from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from typing import cast

import pytest

import app.core.openai.message_coercion as message_coercion
from app.core.openai.chat_requests import ChatCompletionsRequest
from app.core.openai.exceptions import ClientPayloadError
from app.core.openai.requests import ResponsesRequest
from app.core.openai.v1_requests import V1ResponsesCompactRequest, V1ResponsesRequest
from app.core.types import JsonValue

# Synthetic opaque ID: no real provider signature or user data.
OPAQUE_ID = "call_" + "a" * 24 + "__thought__" + "s" * 126


def _messages(call_ids: list[str], alias: str = "tool_call_id") -> list[JsonValue]:
    messages: list[JsonValue] = [{"role": "user", "content": "Run the tool."}]
    for call_id in call_ids:
        messages.extend(
            [
                {
                    "role": "assistant",
                    "content": "Calling.",
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": "lookup", "arguments": '{"key":"value"}'},
                            "extra_content": {"google": {"thought_signature": "synthetic-signature"}},
                        }
                    ],
                },
                {"role": "tool", alias: call_id, "content": "result"},
            ]
        )
    return messages


def _forward(messages: list[JsonValue]) -> list[dict[str, JsonValue]]:
    request = ChatCompletionsRequest.model_validate({"model": "gpt-5.2", "messages": messages})
    payload = request.to_responses_request().model_dump_for_forwarding()
    return cast(list[dict[str, JsonValue]], payload["input"])


def test_chat_forwarding_bounds_incident_call_id_at_input_2() -> None:
    assert len(OPAQUE_ID) == 166
    messages = _messages([OPAQUE_ID])
    original = deepcopy(messages)
    items = _forward(messages)

    assert items[2]["type"] == "function_call"
    assert items[3]["type"] == "function_call_output"
    call_id = items[2]["call_id"]
    assert isinstance(call_id, str)
    assert len(call_id) <= 64
    assert call_id.isascii()
    assert items[3]["call_id"] == call_id
    assert items[2]["arguments"] == '{"key":"value"}'
    assert items[3]["output"] == "result"
    assert messages == original


@pytest.mark.timeout(5)
@pytest.mark.parametrize("short_first", [False, True])
def test_collisions_reserve_all_short_ids_without_merging_links(monkeypatch, short_first: bool) -> None:
    class CollidingDigest:
        def hexdigest(self) -> str:
            return "0" * 64

    monkeypatch.setattr(message_coercion, "sha256", lambda value: CollidingDigest())
    candidate = "call_" + "0" * 32
    short_ids = [candidate, candidate + "_1", "é" * 64]
    long_ids = [OPAQUE_ID, OPAQUE_ID[:-1] + "t", OPAQUE_ID]
    call_ids = short_ids + long_ids if short_first else long_ids + short_ids
    messages = _messages(call_ids)
    original = deepcopy(messages)
    items = _forward(messages)
    calls = [item["call_id"] for item in items if item.get("type") == "function_call"]
    outputs = [item["call_id"] for item in items if item.get("type") == "function_call_output"]

    assert calls == outputs
    assert len(set(calls)) == len(set(call_ids))
    mapping = dict(zip(call_ids, calls, strict=True))
    assert all(mapping[short_id] == short_id for short_id in short_ids)
    assert calls == [mapping[call_id] for call_id in call_ids]
    assert all(isinstance(mapping[call_id], str) and len(str(mapping[call_id])) <= 64 for call_id in long_ids)
    assert all(str(mapping[call_id]).isascii() for call_id in long_ids)
    assert _forward(messages) == items
    assert messages == original


@pytest.mark.parametrize("alias", ["tool_call_id", "toolCallId", "call_id"])
@pytest.mark.parametrize("length", [63, 64, 65])
@pytest.mark.parametrize("character", ["x", "🧪"])
def test_boundaries_and_output_aliases(alias: str, length: int, character: str) -> None:
    original_id = character * length
    items = _forward(_messages([original_id], alias))
    call_id = items[2]["call_id"]
    assert isinstance(call_id, str)
    assert items[3]["call_id"] == call_id
    if length <= 64:
        assert call_id == original_id
        assert call_id.encode("utf-8") == original_id.encode("utf-8")
    else:
        assert len(call_id) <= 64
        assert call_id.isascii()
        assert call_id != original_id
        assert call_id == "call_" + sha256(original_id.encode("utf-8")).hexdigest()[:32]


@pytest.mark.parametrize("route", ["chat", "v1", "compact"])
@pytest.mark.parametrize("surrogate", ["\ud800", "\udfff"], ids=["high", "low"])
@pytest.mark.parametrize("location", ["assistant", "tool_call_id", "toolCallId", "call_id"])
def test_oversized_unencodable_ids_raise_client_payload_error(route: str, surrogate: str, location: str) -> None:
    malformed_id = "x" * 65 + surrogate
    messages = (
        _messages([malformed_id])
        if location == "assistant"
        else [{"role": "tool", location: malformed_id, "content": "result"}]
    )
    source = json.loads(json.dumps({"model": "gpt-5.2", "messages": messages}, ensure_ascii=True))
    original = deepcopy(source)
    # Validation accepts escaped surrogates; rejection belongs to the hashing boundary.
    if route == "chat":
        request = ChatCompletionsRequest.model_validate(source)
    elif route == "v1":
        request = V1ResponsesRequest.model_validate(source)
    else:
        request = V1ResponsesCompactRequest.model_validate(source)
    before = request.model_dump()
    with pytest.raises(ClientPayloadError, match="Oversized tool call identifiers must be valid UTF-8.") as error:
        if isinstance(request, V1ResponsesCompactRequest):
            request.to_compact_request().to_payload()
        else:
            request.to_responses_request().model_dump_for_forwarding()
    assert error.value.param == "messages"
    assert request.model_dump() == before
    assert source == original


def test_full_opaque_ids_repeats_and_normalized_replay_are_stable() -> None:
    ids = [OPAQUE_ID, OPAQUE_ID[:-1] + "t", "🧪" * 65, OPAQUE_ID]
    messages = _messages(ids)
    original = deepcopy(messages)
    request = ChatCompletionsRequest.model_validate({"model": "gpt-5.2", "messages": messages})
    before = request.model_dump(mode="json")
    first = request.to_responses_request().model_dump_for_forwarding()
    second = request.to_responses_request().model_dump_for_forwarding()
    items = cast(list[dict[str, JsonValue]], first["input"])
    calls = [cast(str, item["call_id"]) for item in items if item.get("type") == "function_call"]
    outputs = [item["call_id"] for item in items if item.get("type") == "function_call_output"]
    assert calls == outputs
    assert len(set(calls)) == 3
    assert calls[0] == calls[3]
    assert calls[0] == "call_" + sha256(OPAQUE_ID.encode("utf-8")).hexdigest()[:32]
    assert calls[1] == "call_" + sha256(ids[1].encode("utf-8")).hexdigest()[:32]
    assert first == second
    assert request.model_dump(mode="json") == before
    assert messages == original
    assert _forward(_messages(calls)) == items
    assert _forward(_messages([OPAQUE_ID]))[2]["call_id"] == calls[0]


@pytest.mark.parametrize("alias", ["tool_call_id", "toolCallId", "call_id"])
def test_short_output_only_id_is_reserved_and_mapping_is_request_local(alias: str) -> None:
    candidate = cast(str, _forward(_messages([OPAQUE_ID]))[2]["call_id"])
    messages = _messages([OPAQUE_ID]) + [{"role": "tool", alias: candidate, "content": "unpaired"}]
    items = _forward(messages)
    assert items[-1]["call_id"] == candidate
    assert items[2]["call_id"] != candidate
    assert items[2]["call_id"] == items[3]["call_id"]
    assert _forward(_messages([OPAQUE_ID]))[2]["call_id"] == candidate


@pytest.mark.parametrize("compact", [False, True])
def test_shared_v1_messages_converters_bound_call_ids(compact: bool) -> None:
    source = {"model": "gpt-5.2", "messages": _messages([OPAQUE_ID, OPAQUE_ID])}
    original = deepcopy(source)
    if compact:
        mapped = V1ResponsesCompactRequest.model_validate(source).to_compact_request().to_payload()
    else:
        mapped = V1ResponsesRequest.model_validate(source).to_responses_request().model_dump_for_forwarding()
    items = cast(list[dict[str, JsonValue]], mapped["input"])
    ids = [cast(str, item["call_id"]) for item in items if "call_id" in item]
    assert len(ids) == 4
    assert len(set(ids)) == 1
    assert len(ids[0]) <= 64
    assert ids[0].isascii()
    assert source == original


@pytest.mark.parametrize("route", ["responses", "v1", "compact", "chat", "chat-empty"])
@pytest.mark.parametrize(
    "native_id",
    [OPAQUE_ID, "🧪" * 65, "x" * 65 + "\ud800", "x" * 65 + "\udfff"],
    ids=["opaque", "unicode", "high-surrogate", "low-surrogate"],
)
def test_native_responses_input_is_not_normalized(route: str, native_id: str) -> None:
    native: list[JsonValue] = [
        {"type": "function_call", "call_id": native_id, "name": "lookup", "arguments": "{}"},
        {"type": "function_call_output", "call_id": native_id, "output": "result"},
    ]
    original = deepcopy(native)
    source: dict[str, JsonValue] = {"model": "gpt-5.2", "input": native, "instructions": ""}
    if route == "responses":
        payload = ResponsesRequest.model_validate(source).model_dump_for_forwarding()
    elif route == "v1":
        payload = V1ResponsesRequest.model_validate(source).to_responses_request().model_dump_for_forwarding()
    elif route == "compact":
        payload = V1ResponsesCompactRequest.model_validate(source).to_compact_request().to_payload()
    else:
        if route == "chat-empty":
            source["messages"] = []
        payload = ChatCompletionsRequest.model_validate(source).to_responses_request().model_dump_for_forwarding()
    assert payload["input"] == original
    assert native == original
