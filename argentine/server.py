"""HTTP gate. Local runs bind 127.0.0.1. Fly sets ARGENTINE_BIND=0.0.0.0.

Caller tools are classified by the rubric and never executed.
The process does not open outbound connections.
"""

from __future__ import annotations

import json
import signal
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from argentine.a2a import ParseError, parse_request, peek_brief
from argentine.auth import Allowlist, AllowlistError, bearer_token
from argentine.killswitch import KillSwitch
from argentine.logstore import JsonlLog, build_record, count_decisions
from argentine.rubric import evaluate

DEFAULT_TIMEOUT_S = 15.0
DEFAULT_MAX_CONCURRENT = 2
DEFAULT_RATE_LIMIT = 10
DEFAULT_RATE_WINDOW_S = 3600.0
ALLOWED_BINDS = frozenset({"127.0.0.1", "0.0.0.0"})


class RateLimiter:
    def __init__(self, limit: int, window_s: float) -> None:
        self.limit = limit
        self.window_s = window_s
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, caller: str, now: datetime) -> bool:
        ts = now.timestamp()
        cutoff = ts - self.window_s
        with self._lock:
            queue = self._events.setdefault(caller, deque())
            while queue and queue[0] <= cutoff:
                queue.popleft()
            if len(queue) >= self.limit:
                return False
            queue.append(ts)
            return True


class GateApp:
    def __init__(
        self,
        *,
        allowlist: Allowlist,
        kill: KillSwitch,
        log: JsonlLog,
        now=None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        rate_limit: int = DEFAULT_RATE_LIMIT,
        rate_window_s: float = DEFAULT_RATE_WINDOW_S,
        decide_hook=None,
        port: int = 8787,
    ) -> None:
        self.allowlist = allowlist
        self.kill = kill
        self.log = log
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.timeout_s = timeout_s
        self.max_concurrent = max_concurrent
        self.rate_window_s = rate_window_s
        self.decide_hook = decide_hook
        self.port = port
        self._limiter = RateLimiter(rate_limit, rate_window_s)
        self._slots = threading.BoundedSemaphore(max_concurrent)

    def handle(self, method: str, path: str, headers, body: bytes | None) -> tuple[int, dict]:
        path = urlparse(path).path or "/"
        acquired = self._slots.acquire(blocking=False)
        if not acquired:
            caller = self._caller_label(headers)
            brief = peek_brief(path, body) if method == "POST" and isinstance(body, bytes) else ""
            self._log(caller, brief, None, "NO_GO", ["concurrency_limit"], False, "concurrency_limit")
            return self._respond(503, {"decision": "NO_GO", "fails": ["concurrency_limit"]}, path, body)
        try:
            return self._handle(method, path, headers, body, time.monotonic())
        except Exception as exc:
            self._log("anonymous", "", None, "NO_GO", ["invalid_request"], False, f"internal:{type(exc).__name__}")
            return self._respond(500, {"decision": "NO_GO", "fails": ["invalid_request"]}, path, body)
        finally:
            self._slots.release()

    def _handle(self, method: str, path: str, headers, body: bytes, started: float) -> tuple[int, dict]:
        if method == "GET" and path == "/health":
            return 200, {
                "ok": True,
                "diego_off": self.kill.engaged(),
                "max_concurrent": self.max_concurrent,
                "timeout_seconds": self.timeout_s,
            }
        if method == "GET" and path == "/.well-known/agent-card.json":
            return 200, local_agent_card(self.port)
        if method == "GET" and path == "/v1/gate/stats":
            return self._stats(headers)
        if method != "POST" or path not in {"/v1/gate", "/", "/a2a"}:
            self._log("anonymous", "", None, "NO_GO", ["invalid_request"], False, "invalid_request")
            return self._respond(404, {"decision": "NO_GO", "fails": ["invalid_request"]}, path, body)

        if body is None:
            self._log(self._caller_label(headers), "", None, "NO_GO", ["invalid_request"], False, "invalid_request")
            return self._respond(400, {"decision": "NO_GO", "fails": ["invalid_request"]}, path, b"")

        caller_label = self._caller_label(headers)
        if self.kill.engaged():
            brief = peek_brief(path, body)
            self._log(caller_label, brief, None, "NO_GO", ["diego_off"], False, "diego_off")
            return self._respond(503, {"decision": "NO_GO", "fails": ["diego_off"]}, path, body)

        try:
            caller = self._require_caller(headers)
        except AllowlistError:
            self._log(caller_label, peek_brief(path, body), None, "NO_GO", ["allowlist_unavailable"], False, "allowlist_unavailable")
            return self._respond(503, {"decision": "NO_GO", "fails": ["allowlist_unavailable"]}, path, body)
        if caller is None:
            self._log(caller_label, peek_brief(path, body), None, "NO_GO", ["unauthorized"], False, "unauthorized")
            return self._respond(401, {"decision": "NO_GO", "fails": ["unauthorized"]}, path, body)

        if not self._limiter.allow(caller, self.now()):
            self._log(caller, peek_brief(path, body), None, "NO_GO", ["rate_limited"], False, "rate_limited")
            return self._respond(429, {"decision": "NO_GO", "fails": ["rate_limited"]}, path, body)

        try:
            incoming = parse_request(path, body)
        except ParseError:
            self._log(caller, "", None, "NO_GO", ["invalid_request"], False, "invalid_request")
            return self._respond(400, {"decision": "NO_GO", "fails": ["invalid_request"]}, path, body)

        if self._timed_out(started):
            self._log(caller, incoming.brief, incoming.blast_class, "NO_GO", ["timeout"], False, "timeout")
            return self._respond(504, {"decision": "NO_GO", "fails": ["timeout"]}, path, body, incoming)

        if self.decide_hook is not None:
            self.decide_hook()

        if self._timed_out(started):
            self._log(caller, incoming.brief, incoming.blast_class, "NO_GO", ["timeout"], False, "timeout")
            return self._respond(504, {"decision": "NO_GO", "fails": ["timeout"]}, path, body, incoming)

        decision = evaluate(
            incoming.brief,
            incoming.blast_class,
            incoming.tools,
            incoming.egress,
            now=self.now(),
            human_reject=incoming.human_reject,
        )
        if self._timed_out(started):
            self._log(caller, incoming.brief, decision.blast_class, "NO_GO", ["timeout"], False, "timeout")
            return self._respond(504, {"decision": "NO_GO", "fails": ["timeout"]}, path, body, incoming)

        self._log(
            caller,
            incoming.brief,
            decision.blast_class,
            decision.decision,
            decision.fails,
            decision.human_reject,
            decision.notes,
        )
        payload = {"decision": decision.decision, "fails": list(decision.fails)}
        return self._respond(200, payload, path, body, incoming)

    def _stats(self, headers) -> tuple[int, dict]:
        if self.kill.engaged():
            return 503, {"decision": "NO_GO", "fails": ["diego_off"]}
        try:
            caller = self._require_caller(headers)
        except AllowlistError:
            return 503, {"decision": "NO_GO", "fails": ["allowlist_unavailable"]}
        if caller is None:
            return 401, {"decision": "NO_GO", "fails": ["unauthorized"]}
        human, total = count_decisions(self.log.path)
        return 200, {"human_reject": human, "decisions": total, "ratio": f"{human}/{total}"}

    def _timed_out(self, started: float) -> bool:
        return (time.monotonic() - started) > self.timeout_s

    def _require_caller(self, headers) -> str | None:
        token = bearer_token(headers)
        if not token:
            return None
        return self.allowlist.resolve(token)

    def _caller_label(self, headers) -> str:
        token = bearer_token(headers)
        if not token:
            return "anonymous"
        try:
            return self.allowlist.resolve(token) or "unknown"
        except AllowlistError:
            return "anonymous"

    def _log(
        self,
        caller: str,
        brief: str,
        blast_class: str | None,
        decision: str,
        fails: list[str],
        human_reject: bool,
        notes: str,
    ) -> None:
        record = build_record(
            caller=caller,
            brief=brief,
            blast_class=blast_class,
            decision=decision,
            fails=fails,
            human_reject=human_reject,
            notes=notes,
            now=self.now(),
            record_id=str(uuid.uuid4()),
        )
        self.log.append(record)

    def _respond(self, status: int, payload: dict, path: str, body: bytes | None, incoming=None) -> tuple[int, dict]:
        if path not in {"/", "/a2a"}:
            return status, payload
        rpc_id = incoming.jsonrpc_id if incoming is not None else _peek_rpc_id(body)
        return status, {"jsonrpc": "2.0", "id": rpc_id, "result": payload}


def _peek_rpc_id(body: bytes | None):
    if not body:
        return None
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if isinstance(data, dict):
        return data.get("id")
    return None


def local_agent_card(port: int) -> dict:
    from argentine import ROOT

    card = json.loads((ROOT / "agent-card.json").read_text(encoding="utf-8"))
    card["supportedInterfaces"] = [
        {
            "url": f"http://127.0.0.1:{port}/",
            "protocolBinding": "JSONRPC",
            "protocolVersion": "1.0",
        }
    ]
    return card


def make_handler(app: GateApp):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"
        server_version = "ArGENTine/1.0.0"

        def setup(self) -> None:
            super().setup()
            self.request.settimeout(app.timeout_s)

        def do_GET(self) -> None:
            self._dispatch()

        def do_POST(self) -> None:
            self._dispatch()

        def log_message(self, fmt: str, *args) -> None:
            return

        def _dispatch(self) -> None:
            length_raw = self.headers.get("Content-Length", "0") or "0"
            try:
                length = int(length_raw)
            except ValueError:
                length = -1
            if length < 0 or length > 65_536:
                status, payload = app.handle(self.command, self.path, self.headers, None)
            else:
                body = self.rfile.read(length) if length else b""
                status, payload = app.handle(self.command, self.path, self.headers, body)
            raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            if status == 401:
                self.send_header("WWW-Authenticate", "Bearer")
            self.end_headers()
            self.wfile.write(raw)

    return Handler


def bind(app: GateApp, port: int = 8787, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    """Listen on loopback, or on 0.0.0.0 when a local proxy such as Fly must connect.

    Any other address is refused. Binding 0.0.0.0 does not publish a hostname.
    """
    host = host.strip()
    if host not in ALLOWED_BINDS:
        raise RuntimeError("refusing to bind anything other than 127.0.0.1 or 0.0.0.0")
    handler = make_handler(app)
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    bound_host, bound_port = httpd.server_address[:2]
    if bound_host not in ALLOWED_BINDS:
        httpd.server_close()
        raise RuntimeError("refusing to bind anything other than 127.0.0.1 or 0.0.0.0")
    app.port = bound_port
    return httpd


def serve(app: GateApp, port: int = 8787, host: str = "127.0.0.1") -> None:
    httpd = bind(app, port, host)
    scope = "loopback" if host == "127.0.0.1" else "all interfaces for a local proxy"
    print(
        f"ArGENTine gate listening on http://{host}:{app.port} ({scope})",
        file=sys.stderr,
    )
    print(f"log {app.log.path}", file=sys.stderr)
    print(f"diego off-switch file {app.kill.path}", file=sys.stderr)
    previous = signal.getsignal(signal.SIGTERM)

    def _stop(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _stop)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGTERM, previous)
        httpd.server_close()
