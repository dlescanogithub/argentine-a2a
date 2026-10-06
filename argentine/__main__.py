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
from argentine.auth import Allowlist, AllowlistError
from argentine.killswitch import KillSwitch
from argentine.logstore import DEFAULT_LOG_BACKUPS, DEFAULT_LOG_MAX_BYTES, JsonlLog, count_decisions
from argentine.samples import evaluate_request, load_briefs, parse_now
from argentine.server import ALLOWED_BINDS, GateApp, serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="argentine")
    sub = parser.add_subparsers(dest="cmd", required=True)

    serve_parser = sub.add_parser("serve", help="listen on 127.0.0.1 unless --bind or ARGENTINE_BIND is set")
    serve_parser.add_argument("--port", type=int, default=_env_int("ARGENTINE_PORT", 8787))
    serve_parser.add_argument("--bind", default=os.environ.get("ARGENTINE_BIND", "127.0.0.1"))
    serve_parser.add_argument("--allowlist", type=Path, default=ROOT / "config" / "allowlist.json")
    serve_parser.add_argument(
        "--log",
        type=Path,
        default=Path(os.environ.get("ARGENTINE_LOG_PATH", str(ROOT / "var" / "gate-log.jsonl"))),
    )
    serve_parser.add_argument(
        "--off-file",
        type=Path,
        default=Path(os.environ.get("ARGENTINE_DIEGO_OFF_FILE", str(ROOT / "var" / "diego.off"))),
    )
    serve_parser.add_argument("--rate-limit", type=int, default=_env_int("ARGENTINE_RATE_LIMIT_PER_HOUR", 10))
    serve_parser.add_argument(
        "--log-max-bytes",
        type=int,
        default=_env_int("ARGENTINE_LOG_MAX_BYTES", DEFAULT_LOG_MAX_BYTES),
    )
    serve_parser.add_argument(
        "--log-backups",
        type=int,
        default=_env_int("ARGENTINE_LOG_BACKUPS", DEFAULT_LOG_BACKUPS),
    )
    serve_parser.add_argument(
        "--stdout-log",
        action=argparse.BooleanOptionalAction,
        default=_env_on("ARGENTINE_STDOUT_LOG"),
    )

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
        if str(args.bind).strip() not in ALLOWED_BINDS:
            print("bind must be 127.0.0.1 or 0.0.0.0", file=sys.stderr)
            return 2
        if args.log_max_bytes < 1 or args.log_backups < 0:
            print("log rotation bounds are invalid", file=sys.stderr)
            return 2
        allowlist = Allowlist(path=args.allowlist)
        if _env_on("ARGENTINE_REQUIRE_ALLOWLIST_SECRET") and not os.environ.get("ARGENTINE_ALLOWLIST", "").strip():
            print("ARGENTINE_ALLOWLIST is required", file=sys.stderr)
            return 2
        try:
            allowlist.check()
        except AllowlistError:
            print("allowlist is missing or unreadable", file=sys.stderr)
            return 2
        kill = KillSwitch(args.off_file)
        if _env_on("ARGENTINE_CLEAR_KILL_FILE_ON_BOOT"):
            # Operator clear path: requires a redeploy. Not exposed over HTTP.
            kill.clear_file()
            print(f"cleared diego off-switch file on boot: {args.off_file}", file=sys.stderr)
        admin_token = os.environ.get("ARGENTINE_ADMIN_TOKEN", "").strip() or None
        app = GateApp(
            allowlist=allowlist,
            kill=kill,
            log=JsonlLog(
                args.log,
                max_bytes=args.log_max_bytes,
                backups=args.log_backups,
                stdout=args.stdout_log,
            ),
            rate_limit=args.rate_limit,
            port=args.port,
            admin_token=admin_token,
        )
        serve(app, args.port, str(args.bind).strip())
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


def _env_on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
