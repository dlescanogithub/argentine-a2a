"""Run the local gate, count the log, or check fixture briefs.

    python3 -m argentine serve
    python3 -m argentine count --log fixtures/sample-gate-log.jsonl
    python3 -m argentine decide
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from argentine import ROOT
from argentine.auth import Allowlist
from argentine.killswitch import KillSwitch
from argentine.logstore import JsonlLog, count_decisions
from argentine.samples import evaluate_request, load_briefs, parse_now
from argentine.server import GateApp, serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="argentine")
    sub = parser.add_subparsers(dest="cmd", required=True)

    serve_parser = sub.add_parser("serve", help="listen on 127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=_env_int("ARGENTINE_PORT", 8787))
    serve_parser.add_argument("--allowlist", type=Path, default=ROOT / "config" / "allowlist.json")
    serve_parser.add_argument("--log", type=Path, default=ROOT / "var" / "gate-log.jsonl")
    serve_parser.add_argument("--off-file", type=Path, default=ROOT / "var" / "diego.off")
    serve_parser.add_argument("--rate-limit", type=int, default=_env_int("ARGENTINE_RATE_LIMIT_PER_HOUR", 10))

    count_parser = sub.add_parser("count", help="print human_reject / decisions")
    count_parser.add_argument("--log", type=Path, required=True)

    decide_parser = sub.add_parser("decide", help="score fixture briefs")
    decide_parser.add_argument("--fixtures", type=Path, default=ROOT / "fixtures" / "briefs.json")

    args = parser.parse_args(argv)
    if args.cmd == "serve":
        if args.rate_limit < 1:
            print("rate limit must be at least 1", file=sys.stderr)
            return 2
        if not 0 <= args.port <= 65535:
            print("port must be 0-65535", file=sys.stderr)
            return 2
        app = GateApp(
            allowlist=Allowlist(path=args.allowlist),
            kill=KillSwitch(args.off_file),
            log=JsonlLog(args.log),
            rate_limit=args.rate_limit,
            port=args.port,
        )
        serve(app, args.port)
        return 0
    if args.cmd == "count":
        human, total = count_decisions(args.log)
        print(f"human_reject={human}")
        print(f"decisions={total}")
        print(f"ratio={human}/{total}")
        return 0
    if args.cmd == "decide":
        return _decide(args.fixtures)
    return 2


def _decide(path: Path) -> int:
    payload = load_briefs(path)
    default_now = parse_now(payload.get("now") or "2026-09-30T12:00:00Z")
    failed = 0
    for case in payload["cases"]:
        now = parse_now(case["now"]) if case.get("now") else default_now
        result = evaluate_request(case["request"], now)
        expect = case["expect"]
        ok = result.decision == expect["decision"] and result.fails == expect["fails"]
        mark = "ok" if ok else "MISMATCH"
        print(f"{case['name']} {result.decision} {json.dumps(result.fails)} {mark}")
        if not ok:
            failed += 1
            print(
                f"  expected {expect['decision']} {json.dumps(expect['fails'])}",
                file=sys.stderr,
            )
    return 1 if failed else 0


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


if __name__ == "__main__":
    raise SystemExit(main())
