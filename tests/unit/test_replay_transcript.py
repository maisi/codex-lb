from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from app.core.openai.requests import ResponsesRequest
from app.core.types import JsonValue
from app.modules.proxy import replay_transcript
from app.modules.proxy.durable_bridge_repository import DurableBridgeOperationSnapshot, DurableBridgeTranscriptTurn

pytestmark = pytest.mark.unit


def _message(role: str, text: str, **fields: JsonValue) -> dict[str, JsonValue]:
    return {
        "type": "message",
        "role": role,
        "content": [{"type": "output_text" if role == "assistant" else "input_text", "text": text}],
        **fields,
    }


def _turn(
    input_items: list[JsonValue],
    output: list[JsonValue],
    *,
    response_id: str = "resp-1",
    parent: str | None = None,
    event_type: str = "response.completed",
) -> DurableBridgeTranscriptTurn:
    return DurableBridgeTranscriptTurn(
        operation=DurableBridgeOperationSnapshot(
            operation_id=f"operation-{response_id}",
            session_id="session-1",
            request_fingerprint="fingerprint",
            account_id="owner-1",
            model="gpt-5.1",
            parent_response_id=parent,
            state="incomplete" if event_type == "response.incomplete" else "completed",
            response_id=response_id,
            request_text=json.dumps({"model": "gpt-5.1", "input": input_items, "previous_response_id": parent}),
        ),
        events=(f"data: {json.dumps({'type': event_type, 'response': {'id': response_id, 'output': output}})}\n\n",),
    )


def _rebuild(
    turns: list[DurableBridgeTranscriptTurn],
    current: JsonValue,
    *,
    anchor: str = "resp-1",
) -> list[JsonValue] | None:
    payload = ResponsesRequest.model_validate(
        {"model": "gpt-5.1", "instructions": "", "input": current, "previous_response_id": anchor}
    )
    return replay_transcript.rebuild_transcript_input(
        turns, payload=payload, anchor_response_id=anchor, session_id="session-1", account_id="owner-1"
    )


@pytest.mark.parametrize("client_form", ["delta", "full", "rolling", "ends_at_tail", "coincidence"])
def test_rebuild_preserves_wire_input_and_only_replaces_matching_tail(client_form: str) -> None:
    question = _message("user", "first", id="input-1")
    answer = _message("assistant", "answer", id="output-1", status="completed", phase="final_answer")
    current = _message("user", "next")
    turn = _turn([question], [answer])
    client_inputs = {
        "delta": [current],
        "full": [_message("user", "first"), _message("assistant", "answer"), current],
        "rolling": [_message("assistant", "answer"), current],
        "ends_at_tail": [_message("assistant", "answer")],
        "coincidence": [_message("user", "first")],
    }
    result = _rebuild([turn], cast(JsonValue, client_inputs[client_form]))
    assert result is not None
    texts = [cast(dict[str, JsonValue], item)["content"] for item in result]
    expected = {
        "delta": [question["content"], answer["content"], current["content"]],
        "full": [question["content"], answer["content"], current["content"]],
        "rolling": [question["content"], answer["content"], current["content"]],
        "ends_at_tail": [question["content"], answer["content"]],
        "coincidence": [question["content"], answer["content"], question["content"]],
    }
    assert texts == expected[client_form]
    assert all("id" not in cast(dict[str, JsonValue], item) for item in result)


def test_rebuild_assembles_multiple_turns_oldest_first() -> None:
    first, answer = _message("user", "first"), _message("assistant", "answer")
    second, next_answer = _message("user", "second"), _message("assistant", "second answer")
    third = _message("user", "third")
    turns = [_turn([first], [answer]), _turn([answer, second], [next_answer], response_id="resp-2", parent="resp-1")]
    assert _rebuild(turns, [third], anchor="resp-2") == [first, answer, second, next_answer, third]
    assert _rebuild(list(reversed(turns)), [third], anchor="resp-2") is None


@pytest.mark.parametrize("kind", ["function", "custom", "apply_patch"])
def test_rebuild_retains_and_settles_each_portable_tool_kind(kind: str) -> None:
    wire_kind = "custom_tool" if kind == "custom" else kind
    call: dict[str, JsonValue] = {"type": f"{wire_kind}_call", "call_id": "call-1", "id": "recording-1"}
    if kind == "function":
        call.update(name="shell", arguments='{"command":"pwd"}')
    elif kind == "custom":
        call.update(name="shell", input="pwd")
    else:
        call["operation"] = {"type": "update_file", "path": "file.txt", "diff": "new text"}
    output: JsonValue = {"type": f"{wire_kind}_call_output", "call_id": "call-1", "output": "ok"}
    question = _message("user", "do the work")
    result = _rebuild([_turn([question], [call])], [output, _message("user", "continue")])
    assert result is not None
    assert len(result) == 4
    assert _rebuild([_turn([question], [call])], [_message("user", "continue")]) is None


def test_rebuild_tool_bundle_comparison_ignores_nested_recording_descriptions() -> None:
    old: JsonValue = {
        "type": "additional_tools",
        "role": "developer",
        "tools": [{"type": "function", "name": "shell", "description": "old wording"}],
    }
    new: JsonValue = {
        "type": "additional_tools",
        "role": "developer",
        "tools": [{"type": "function", "name": "shell", "description": "new wording"}],
    }
    question, answer, current = _message("user", "first"), _message("assistant", "answer"), _message("user", "next")
    assert _rebuild([_turn([old, question], [answer])], [new, question, answer, current]) == [
        new,
        question,
        answer,
        current,
    ]


@pytest.mark.parametrize(
    "invalid",
    [
        {"type": "item_reference", "id": "account-owned"},
        {"type": "input_file", "file_id": "file-account-owned"},
        {"type": "function_call_output", "call_id": "orphan", "output": "ok"},
        {"role": "user", "content": [{"type": "input_text", "text": "hi", "unknown": {"file_id": "file-1"}}]},
        {"type": "reasoning", "id": "unknown-owned-reasoning", "encrypted_content": "account-owned"},
    ],
)
def test_rebuild_refuses_account_state_unknown_nested_fields_and_orphan_tools(invalid: JsonValue) -> None:
    assert _rebuild([_turn([_message("user", "first")], [_message("assistant", "answer")])], [invalid]) is None


@pytest.mark.parametrize("fault", ["scope", "owner", "missing_parent", "cycle", "incomplete", "failure", "wrong_id"])
def test_rebuild_refuses_corrupt_or_unsettled_transcript(fault: str) -> None:
    turn = _turn([_message("user", "first")], [_message("assistant", "answer")])
    operations = {
        "scope": replace(turn.operation, session_id="another-key-session"),
        "owner": replace(turn.operation, account_id="another-owner"),
        "missing_parent": replace(turn.operation, parent_response_id="missing"),
        "cycle": replace(turn.operation, parent_response_id="resp-1"),
        "incomplete": replace(turn.operation, event_spool_complete=False),
        "failure": replace(turn.operation, state="failed"),
        "wrong_id": replace(turn.operation, response_id="other-response"),
    }
    assert _rebuild([replace(turn, operation=operations[fault])], [_message("user", "next")]) is None


def test_rebuild_incomplete_answer_uses_output_item_done_when_terminal_has_no_output() -> None:
    question, answer = _message("user", "first"), _message("assistant", "answer")
    turn = _turn([question], [], event_type="response.incomplete")
    events = (
        f"data: {json.dumps({'type': 'response.output_item.done', 'item': answer})}\n\n",
        'data: {"type":"response.incomplete","response":{"id":"resp-1"}}\n\n',
    )
    assert _rebuild([replace(turn, events=events)], [_message("user", "next")]) == [
        question,
        answer,
        _message("user", "next"),
    ]
    assert _rebuild([replace(turn, events=events[:1])], [_message("user", "next")]) is None
    assert _rebuild([_turn([question], [answer], event_type="response.failed")], [_message("user", "next")]) is None


@pytest.mark.parametrize(
    "bound", ["TRANSCRIPT_REPLAY_MAX_TURNS", "TRANSCRIPT_REPLAY_MAX_BYTES", "TRANSCRIPT_REPLAY_MAX_ITEMS"]
)
def test_rebuild_enforces_actual_production_bounds(monkeypatch: pytest.MonkeyPatch, bound: str) -> None:
    monkeypatch.setattr(replay_transcript, bound, 1)
    first = _turn([_message("user", "first")], [_message("assistant", "answer")])
    turns = [first]
    anchor = "resp-1"
    if bound == "TRANSCRIPT_REPLAY_MAX_TURNS":
        turns.append(_turn([_message("user", "second")], [], response_id="resp-2", parent="resp-1"))
        anchor = "resp-2"
    assert _rebuild(turns, [_message("user", "next")], anchor=anchor) is None


def test_rebuild_byte_budget_is_whole_transcript(monkeypatch: pytest.MonkeyPatch) -> None:
    question, answer = _message("user", "first"), _message("assistant", "answer")
    turn = _turn([question], [answer])
    assert turn.operation.request_text is not None
    one_turn_bytes = len(turn.operation.request_text.encode()) + sum(len(event.encode()) for event in turn.events)
    monkeypatch.setattr(replay_transcript, "TRANSCRIPT_REPLAY_MAX_BYTES", one_turn_bytes + 400)
    turns = [turn, _turn([question], [answer], response_id="resp-2", parent="resp-1")]
    assert _rebuild(turns, [_message("user", "next")], anchor="resp-2") is None


def test_rebuild_refuses_unrecorded_lite_developer_id() -> None:
    bundle: JsonValue = {"type": "additional_tools", "role": "developer", "tools": []}
    assert (
        _rebuild(
            [_turn([_message("user", "first")], [_message("assistant", "answer")])],
            [bundle, {"role": "developer", "id": "unknown-owned-instruction", "content": "changed"}],
        )
        is None
    )


@pytest.mark.parametrize("annotations", [[], [{"type": "file_citation", "file_id": "file-owned"}]])
def test_rebuild_realistic_output_text_bookkeeping(annotations: list[JsonValue]) -> None:
    question, answer, current = _message("user", "first"), _message("assistant", "answer"), _message("user", "next")
    recorded: JsonValue = {
        **answer,
        "content": [{"type": "output_text", "text": "answer", "annotations": annotations, "logprobs": []}],
    }
    result = _rebuild([_turn([question], [recorded])], [current])
    assert result == ([question, answer, current] if not annotations else None)


@pytest.mark.parametrize("fault", ["event_owner", "state", "missing_output", "after_terminal", "body_parent"])
def test_rebuild_refuses_inconsistent_terminal_and_item_events(fault: str) -> None:
    question = _message("user", "first")
    answer = _message("assistant", "answer", id="output-1")
    turn = _turn([question], [answer])
    done = f"data: {json.dumps({'type': 'response.output_item.done', 'response_id': 'resp-1', 'item': answer})}\n\n"
    if fault == "event_owner":
        turn = replace(turn, events=(done.replace('"resp-1"', '"foreign-response"'), *turn.events))
    elif fault == "state":
        turn = replace(turn, operation=replace(turn.operation, state="incomplete"))
    elif fault == "missing_output":
        turn = replace(_turn([question], []), events=(done, *_turn([question], []).events))
    elif fault == "after_terminal":
        turn = replace(turn, events=(*turn.events, done))
    else:
        turn = replace(
            turn,
            operation=replace(
                turn.operation, request_text=json.dumps({"input": [question], "previous_response_id": "missing"})
            ),
        )
    assert _rebuild([turn], [_message("user", "next")]) is None
