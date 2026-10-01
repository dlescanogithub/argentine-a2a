#!/usr/bin/env python3
"""POST a brief to the live ArGENTine gate and print decision plus fails.

The bearer token comes from ARGENTINE_CALLER_TOKEN and is never printed.
This script is a local caller. The gate package does not import it.

    export ARGENTINE_CALLER_TOKEN="your-allowlist-token"
    python3 scripts/call_gate.py go
    python3 scripts/call_gate.py need-human
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIEFS_PATH = ROOT / "fixtures" / "briefs.json"
DEFAULT_GATE_URL = "https://argentine-a2a-production.up.railway.app/v1/gate"
TIMEOUT_S = 20.0

# Short names for the two demo briefs in fixtures/briefs.json.
CASE_ALIASES = {
    "go": "low-complete",
    "need-human": "high-missing",
}


class UsageError(Exception):
    pass


class CallError(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects so the bearer token stays on the requested host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def build_opener():
    return urllib.request.build_opener(_NoRedirect)


def main(argv: list[str] | None = None, *, env: dict | None = None, post=None) -> int:
    env = os.environ if env is None else env
    try:
        request = build_request(argv)
    except UsageError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    token = env.get("ARGENTINE_CALLER_TOKEN", "").strip()
    if not token:
        print("ARGENTINE_CALLER_TOKEN is required", file=sys.stderr)
        return 2
    url = env.get("ARGENTINE_GATE_URL", "").strip() or DEFAULT_GATE_URL
    send = post or http_post
    try:
        _status, body = send(url, token, request)
    except CallError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return _emit(body, token)


def build_request(argv: list[str] | None) -> dict:
    parser = argparse.ArgumentParser(
        prog="scripts/call_gate.py",
        description="POST a brief to the ArGENTine gate. Prints decision and fails only.",
    )
    parser.add_argument(
        "case",
        nargs="?",
        help="fixture name, or go (low-complete) / need-human (high-missing)",
    )
    parser.add_argument("--brief", help="inline brief text")
    parser.add_argument("--blast-class", choices=("low", "medium", "high"))
    parser.add_argument("--tools", action="append", default=[], metavar="NAME")
    parser.add_argument("--egress", action="append", default=[], metavar="NAME")
    args = parser.parse_args(argv)
    inline = bool(args.brief or args.blast_class or args.tools or args.egress)
    if args.case and inline:
        raise UsageError("pass a case name or inline flags, not both")
    if args.case:
        return case_request(args.case)
    if not args.brief:
        raise UsageError("pass a case name (go, need-human, or a fixture) or --brief")
    request: dict = {"brief": args.brief}
    if args.blast_class:
        request["blast_class"] = args.blast_class
    if args.tools:
        request["tools"] = list(args.tools)
    if args.egress:
        request["egress"] = list(args.egress)
    return request


def case_request(name: str) -> dict:
    wanted = CASE_ALIASES.get(name, name)
    try:
        payload = json.loads(BRIEFS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UsageError("fixtures/briefs.json is unreadable") from exc
    for case in payload.get("cases", []):
        if case.get("name") == wanted:
            request = case.get("request")
            if not isinstance(request, dict) or not isinstance(request.get("brief"), str):
                raise UsageError(f"fixture {wanted} has no brief")
            return request
    raise UsageError(f"unknown case {name!r}")


def http_post(url: str, token: str, payload: dict, *, opener=None, timeout: float = TIMEOUT_S) -> tuple[int, dict]:
    data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    client = opener or build_opener()
    try:
        with client.open(req, timeout=timeout) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None) or resp.getcode()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    except Exception as exc:
        raise CallError("gate request failed") from exc
    return status, _decode_body(raw)


def _decode_body(raw: bytes) -> dict:
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CallError("gate response was not JSON") from exc
    if not isinstance(body, dict):
        raise CallError("gate response was not JSON")
    return body


def _emit(body: dict, token: str) -> int:
    decision = body.get("decision")
    fails = body.get("fails")
    if not isinstance(decision, str) or not isinstance(fails, list):
        print("gate response missing decision and fails", file=sys.stderr)
        return 1
    try:
        line = json.dumps(
            {"decision": decision, "fails": fails},
            ensure_ascii=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        print("gate response missing decision and fails", file=sys.stderr)
        return 1
    if token in line:
        print("refusing to print a response that includes the caller token", file=sys.stderr)
        return 1
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
