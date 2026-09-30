"""Parse a gate request from the REST body or an A2A JSON-RPC message/send.

No URL in the payload is fetched. Push-notification and callback fields are ignored.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

MAX_BODY = 65_536
MAX_BRIEF = 32_768
MAX_LIST = 64


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class Incoming:
    brief: str
    blast_class: str | None
    tools: list[str] | None
    egress: list[str] | None
    human_reject: bool | None
    jsonrpc_id: object
    is_jsonrpc: bool


def parse_request(path: str, body: bytes) -> Incoming:
    if len(body) > MAX_BODY:
        raise ParseError("invalid_request")
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ParseError("invalid_request") from exc
    if not isinstance(data, dict):
        raise ParseError("invalid_request")
    if path in {"/", "/a2a"}:
        return _parse_rpc(data)
    return _parse_rest(data)


def peek_brief(path: str, body: bytes) -> str:
    try:
        return parse_request(path, body).brief
    except ParseError:
        return ""


def _parse_rest(data: dict) -> Incoming:
    if "brief" not in data or not isinstance(data["brief"], str):
        raise ParseError("invalid_request")
    if len(data["brief"]) > MAX_BRIEF:
        raise ParseError("invalid_request")
    return Incoming(
        brief=data["brief"],
        blast_class=_optional_str(data, "blast_class"),
        tools=_optional_list(data, "tools"),
        egress=_optional_list(data, "egress"),
        human_reject=_optional_bool(data, "human_reject"),
        jsonrpc_id=None,
        is_jsonrpc=False,
    )


def _parse_rpc(data: dict) -> Incoming:
    if data.get("jsonrpc") != "2.0" or data.get("method") != "message/send":
        raise ParseError("invalid_request")
    params = data.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ParseError("invalid_request")
    message = params.get("message")
    if not isinstance(message, dict):
        raise ParseError("invalid_request")
    parts = message.get("parts")
    if not isinstance(parts, list):
        raise ParseError("invalid_request")
    texts: list[str] = []
    merged: dict = {}
    for part in parts:
        if not isinstance(part, dict):
            raise ParseError("invalid_request")
        kind = part.get("kind", part.get("type"))
        if kind == "text":
            text = part.get("text")
            if not isinstance(text, str):
                raise ParseError("invalid_request")
            texts.append(text)
        elif kind == "data":
            payload = part.get("data")
            if not isinstance(payload, dict):
                raise ParseError("invalid_request")
            merged.update(payload)
        else:
            raise ParseError("invalid_request")
    brief = "\n".join(texts).strip()
    if not brief and isinstance(merged.get("brief"), str):
        brief = merged["brief"]
    if not isinstance(brief, str) or brief == "":
        raise ParseError("invalid_request")
    if len(brief) > MAX_BRIEF:
        raise ParseError("invalid_request")
    # Callback URLs, if a client sent them, are not read and not called.
    return Incoming(
        brief=brief,
        blast_class=_optional_str(merged, "blast_class"),
        tools=_optional_list(merged, "tools"),
        egress=_optional_list(merged, "egress"),
        human_reject=_optional_bool(merged, "human_reject"),
        jsonrpc_id=data.get("id"),
        is_jsonrpc=True,
    )


def _optional_str(data: dict, key: str) -> str | None:
    if key not in data or data[key] is None:
        return None
    value = data[key]
    if not isinstance(value, str):
        raise ParseError("invalid_request")
    return value


def _optional_bool(data: dict, key: str) -> bool | None:
    if key not in data or data[key] is None:
        return None
    value = data[key]
    if not isinstance(value, bool):
        raise ParseError("invalid_request")
    return value


def _optional_list(data: dict, key: str) -> list[str] | None:
    if key not in data or data[key] is None:
        return None
    value = data[key]
    if isinstance(value, str):
        parts = [item.strip() for item in value.split(",") if item.strip()]
        if len(parts) > MAX_LIST:
            raise ParseError("invalid_request")
        return parts
    if isinstance(value, list):
        if len(value) > MAX_LIST:
            raise ParseError("invalid_request")
        items: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ParseError("invalid_request")
            if item.strip():
                items.append(item.strip())
        return items
    raise ParseError("invalid_request")
