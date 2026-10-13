"""Bounded, portable reconstruction of a settled bridge conversation."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import cast

from app.core.openai.requests import ResponsesRequest
from app.core.types import JsonValue
from app.core.utils.sse import parse_sse_data_json
from app.modules.proxy.durable_bridge_repository import DurableBridgeTranscriptTurn
from app.modules.proxy.replay_safety import (
    project_responses_input_for_account_neutral_fresh_replay,
    responses_input_items_have_account_neutral_shape,
    responses_payload_is_account_neutral_fresh_replay,
)

TRANSCRIPT_REPLAY_MAX_TURNS = 128
TRANSCRIPT_REPLAY_MAX_BYTES = 8 * 1024 * 1024
TRANSCRIPT_REPLAY_MAX_ITEMS = 8192


def _content_key(content: JsonValue) -> JsonValue | None:
    if isinstance(content, str):
        return [["text", content]]
    if not isinstance(content, list):
        return None
    parts: list[JsonValue] = []
    for part in content:
        if not isinstance(part, dict):
            return None
        kind = part.get("type")
        if kind in ("input_text", "output_text", "text") and isinstance(part.get("text"), str):
            parts.append(["text", part["text"]])
        elif kind == "refusal" and isinstance(part.get("refusal"), str):
            parts.append(["refusal", part["refusal"]])
        elif kind == "input_image" and isinstance(part.get("image_url"), str):
            parts.append(["image", part["image_url"], part.get("detail")])
        elif kind == "input_file":
            data = part.get("file_data")
            url = part.get("file_url")
            if isinstance(data, str):
                parts.append(["file_data", data, part.get("filename")])
            elif isinstance(url, str):
                parts.append(["file_url", url, part.get("filename")])
            else:
                return None
        else:
            return None
    return parts


def _item_key(item: JsonValue) -> str | None:
    if not isinstance(item, dict):
        return None
    kind = item.get("type", "message")
    key: JsonValue
    if kind == "message":
        content = _content_key(item.get("content"))
        if content is None or not isinstance(item.get("role"), str):
            return None
        key = ["message", item["role"], content]
    elif kind in ("input_text", "output_text", "text", "refusal", "input_image", "input_file"):
        content = _content_key([item])
        if content is None:
            return None
        key = ["content", content]
    elif kind in ("function_call", "custom_tool_call"):
        argument_field = "arguments" if kind == "function_call" else "input"
        if not all(isinstance(item.get(field), str) for field in ("call_id", "name", argument_field)):
            return None
        key = [kind, item["call_id"], item["name"], item[argument_field]]
    elif kind == "apply_patch_call":
        if not isinstance(item.get("call_id"), str):
            return None
        if "operation" in item:
            operation = item["operation"]
            if not isinstance(operation, dict) or not all(
                isinstance(operation.get(field), str) for field in ("type", "path")
            ):
                return None
            if operation["type"] == "delete_file":
                patch: JsonValue = [operation["type"], operation["path"]]
            elif operation["type"] in ("create_file", "update_file") and isinstance(operation.get("diff"), str):
                patch = [operation["type"], operation["path"], operation["diff"]]
            else:
                return None
        elif isinstance(item.get("patch"), str):
            patch = ["patch", item["patch"]]
        elif isinstance(item.get("input"), str):
            patch = ["input", item["input"]]
        else:
            return None
        key = [kind, item["call_id"], patch]
    elif kind in ("function_call_output", "custom_tool_call_output", "apply_patch_call_output"):
        if not isinstance(item.get("call_id"), str):
            return None
        output = item.get("output")
        output_key: JsonValue
        if output is None and kind == "apply_patch_call_output":
            output_key = ["status", item.get("status")]
        elif isinstance(output, str):
            output_key = ["text", output]
        else:
            output_key = _content_key(output)
            if output_key is None:
                return None
        key = [kind, item["call_id"], output_key]
    elif kind == "additional_tools":
        tools = item.get("tools")
        if not isinstance(tools, list):
            return None
        tool_keys: list[JsonValue] = []
        for tool in tools:
            if not isinstance(tool, dict) or not isinstance(tool.get("type"), str):
                return None
            name = tool.get("name")
            if tool["type"] in ("function", "custom"):
                if not isinstance(name, str):
                    return None
                tool_keys.append([tool["type"], name])
            elif tool["type"] in ("web_search", "web_search_preview"):
                tool_keys.append([tool["type"]])
            else:
                return None
        key = [kind, item.get("role"), tool_keys]
    else:
        return None
    return json.dumps(key, ensure_ascii=False, separators=(",", ":"))


def _join_tail(history: list[JsonValue], current: list[JsonValue]) -> list[JsonValue] | None:
    """Replace only a matching stored tail; never discard a current item."""
    if not current:
        return list(history)
    current_keys = [_item_key(item) for item in current]
    history_keys = [_item_key(item) for item in history]
    if any(key is None for key in (*current_keys, *history_keys)):
        return None
    # KMP computes the longest current prefix that is a suffix of history.
    # None is a unique separator because unidentified items were refused.
    keys = [*current_keys, None, *history_keys]
    prefix = [0] * len(keys)
    for index in range(1, len(keys)):
        matched = prefix[index - 1]
        while matched and keys[index] != keys[matched]:
            matched = prefix[matched - 1]
        if keys[index] == keys[matched]:
            matched += 1
        prefix[index] = matched
    overlap = prefix[-1]
    return [*(history[:-overlap] if overlap else history), *current]


def _project(items: list[JsonValue]) -> list[JsonValue] | None:
    if not items:
        return []
    if any(isinstance(item, dict) and item.get("id") is not None and not isinstance(item["id"], str) for item in items):
        return None
    projection = project_responses_input_for_account_neutral_fresh_replay(items, stored_count=len(items))
    if projection is None:
        return None
    normalized: list[JsonValue] = []
    for item in projection.input_items:
        # Responses emits these empty output bookkeeping fields on ordinary
        # assistant text. Nonempty annotations can carry account-owned files
        # and are deliberately left for the strict shape check to reject.
        if isinstance(item, dict) and item.get("role") == "assistant" and isinstance(item.get("content"), list):
            parts: list[JsonValue] = []
            for part in cast(list[JsonValue], item["content"]):
                if isinstance(part, dict) and part.get("type") == "output_text":
                    part = {
                        key: value
                        for key, value in part.items()
                        if key not in ("annotations", "logprobs") or value != []
                    }
                parts.append(part)
            item = {**item, "content": parts}
        normalized.append(item)
    return normalized if responses_input_items_have_account_neutral_shape(normalized) else None


def _settled_output(turn: DurableBridgeTranscriptTurn) -> list[JsonValue] | None:
    output_items: list[JsonValue] = []
    terminal_output: list[JsonValue] | None = None
    settled = False
    for event_text in turn.events:
        event = parse_sse_data_json(event_text)
        if not isinstance(event, dict):
            return None
        event_type = event.get("type")
        if event_type in ("error", "response.failed"):
            return None
        if event_type == "response.output_item.done":
            if settled or event.get("response_id") not in (None, turn.operation.response_id):
                return None
            item = event.get("item")
            if not isinstance(item, dict):
                return None
            output_items.append(item)
        elif event_type in ("response.completed", "response.incomplete"):
            response = event.get("response")
            if (
                settled
                or event_type != f"response.{turn.operation.state}"
                or not isinstance(response, dict)
                or response.get("id") != turn.operation.response_id
            ):
                return None
            settled = True
            output = response.get("output")
            if output is not None:
                if not isinstance(output, list):
                    return None
                terminal_output = output
    if terminal_output is not None:
        terminal_ids = {
            item.get("id") for item in terminal_output if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        if any(
            isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"] not in terminal_ids
            for item in output_items
        ):
            return None
    return (terminal_output if terminal_output is not None else output_items) if settled else None


def rebuild_transcript_input(
    transcript: Sequence[DurableBridgeTranscriptTurn],
    *,
    payload: ResponsesRequest,
    anchor_response_id: str,
    session_id: str,
    account_id: str,
) -> list[JsonValue] | None:
    if not transcript or len(transcript) > TRANSCRIPT_REPLAY_MAX_TURNS or not isinstance(payload.input, list):
        return None
    total_bytes = len(payload.model_dump_json().encode("utf-8"))
    item_count = len(payload.input)
    history: list[JsonValue] = []
    seen: set[str] = set()
    previous_response_id: str | None = None
    recorded_ids: set[str] = set()
    for turn in transcript:
        operation = turn.operation
        response_id = operation.response_id
        if (
            operation.session_id != session_id
            or operation.account_id != account_id
            or operation.state not in ("completed", "incomplete")
            or not operation.event_spool_complete
            or operation.request_text is None
            or response_id is None
            or response_id in seen
            or operation.parent_response_id != previous_response_id
        ):
            return None
        seen.add(response_id)
        previous_response_id = response_id
        total_bytes += len(operation.request_text.encode("utf-8")) + sum(
            len(event.encode("utf-8")) for event in turn.events
        )
        if total_bytes > TRANSCRIPT_REPLAY_MAX_BYTES:
            return None
        try:
            request = json.loads(operation.request_text)
        except (ValueError, TypeError):
            return None
        if (
            not isinstance(request, dict)
            or not isinstance(request.get("input"), list)
            or request.get("conversation") not in (None, "")
            or request.get("prompt") not in (None, "")
            or (request.get("previous_response_id") or None) != operation.parent_response_id
        ):
            return None
        output = _settled_output(turn)
        if output is None:
            return None
        items = cast(list[JsonValue], request["input"])
        item_count += len(items) + len(output)
        if item_count > TRANSCRIPT_REPLAY_MAX_ITEMS:
            return None
        for item in (*items, *output):
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                recorded_ids.add(cast(str, item["id"]))
        projected_input, projected_output = _project(items), _project(output)
        if projected_input is None or projected_output is None:
            return None
        joined = _join_tail(history, projected_input)
        if joined is None:
            return None
        history = [*joined, *projected_output]
    if previous_response_id != anchor_response_id:
        return None
    for item in payload.input:
        # Only recorded bookkeeping may be removed from a new request. A new
        # response-owned developer item or reasoning reference is not proof of
        # portable current input merely because its ID could be stripped.
        if isinstance(item, dict) and (item.get("role") == "developer" or item.get("type") == "reasoning"):
            item_id = item.get("id")
            if (item.get("type") == "reasoning" or item_id is not None) and (
                not isinstance(item_id, str) or item_id not in recorded_ids
            ):
                return None
    current = _project(payload.input)
    if current is None:
        return None
    rebuilt = _join_tail(history, current)
    if rebuilt is None or len(rebuilt) > TRANSCRIPT_REPLAY_MAX_ITEMS:
        return None
    fresh = payload.model_copy(update={"input": rebuilt, "previous_response_id": None})
    if not responses_payload_is_account_neutral_fresh_replay(fresh.to_replay_safety_payload()):
        return None
    if len(fresh.model_dump_json().encode("utf-8")) > TRANSCRIPT_REPLAY_MAX_BYTES:
        return None
    return rebuilt
