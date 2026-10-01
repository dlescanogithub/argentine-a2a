"""Caller demo: fixture briefs, inline flags, and a mocked gate POST."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from argentine import ROOT
from argentine.samples import load_briefs

TOKEN = "test-caller-token"
SCRIPT = ROOT / "scripts" / "call_gate.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("call_gate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


call_gate = _load_script()


def _fixture(name: str) -> dict:
    briefs = load_briefs()
    for case in briefs["cases"]:
        if case["name"] == name:
            return case["request"]
    raise AssertionError(name)


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.server.captured = {
            "path": self.path,
            "authorization": self.headers.get("Authorization"),
            "body": body,
        }
        payload = b'{"decision":"NEED_HUMAN","fails":["hitl","approved_until","digest","kill_path"]}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args) -> None:
        return


class CallGateTest(unittest.TestCase):
    def test_go_and_need_human_match_fixtures(self) -> None:
        self.assertEqual(call_gate.case_request("go"), _fixture("low-complete"))
        self.assertEqual(call_gate.case_request("need-human"), _fixture("high-missing"))
        self.assertEqual(call_gate.case_request("high-reject"), _fixture("high-reject"))

    def test_missing_token_does_not_post(self) -> None:
        called = []

        def post(url, token, payload):
            called.append((url, token, payload))
            return 200, {"decision": "GO", "fails": []}

        code, out, err = _run(["go"], {}, post)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("ARGENTINE_CALLER_TOKEN is required", err)
        self.assertEqual(called, [])

    def test_posts_go_and_prints_only_decision(self) -> None:
        seen = {}

        def post(url, token, payload):
            seen["url"] = url
            seen["token"] = token
            seen["payload"] = payload
            return 200, {"decision": "GO", "fails": [], "notes": TOKEN}

        code, out, err = _run(["go"], {"ARGENTINE_CALLER_TOKEN": TOKEN}, post)
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(out, '{"decision":"GO","fails":[]}\n')
        self.assertNotIn(TOKEN, out)
        self.assertEqual(seen["url"], call_gate.DEFAULT_GATE_URL)
        self.assertEqual(seen["token"], TOKEN)
        self.assertEqual(seen["payload"], _fixture("low-complete"))

    def test_need_human_and_custom_url(self) -> None:
        seen = {}

        def post(url, token, payload):
            seen["url"] = url
            seen["payload"] = payload
            return 200, {"decision": "NEED_HUMAN", "fails": ["hitl", "approved_until", "digest", "kill_path"]}

        env = {
            "ARGENTINE_CALLER_TOKEN": TOKEN,
            "ARGENTINE_GATE_URL": "https://gate.example/v1/gate",
        }
        code, out, err = _run(["need-human"], env, post)
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(
            out,
            '{"decision":"NEED_HUMAN","fails":["hitl","approved_until","digest","kill_path"]}\n',
        )
        self.assertNotIn(TOKEN, out)
        self.assertEqual(seen["url"], "https://gate.example/v1/gate")
        self.assertEqual(seen["payload"], _fixture("high-missing"))

    def test_inline_flags(self) -> None:
        seen = {}

        def post(url, token, payload):
            seen["payload"] = payload
            return 200, {"decision": "NEED_HUMAN", "fails": ["hitl"]}

        code, out, err = _run(
            [
                "--brief",
                "Review whether to draft a participation note.",
                "--blast-class",
                "high",
                "--egress",
                "reply",
                "--tools",
                "draft",
            ],
            {"ARGENTINE_CALLER_TOKEN": TOKEN},
            post,
        )
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(seen["payload"]["brief"], "Review whether to draft a participation note.")
        self.assertEqual(seen["payload"]["blast_class"], "high")
        self.assertEqual(seen["payload"]["egress"], ["reply"])
        self.assertEqual(seen["payload"]["tools"], ["draft"])
        self.assertNotIn(TOKEN, out)

    def test_unknown_case_and_mixed_flags(self) -> None:
        code, out, err = _run(["missing-case"], {"ARGENTINE_CALLER_TOKEN": TOKEN}, _unused_post)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("unknown case", err)
        self.assertNotIn(TOKEN, err)

        code, out, err = _run(
            ["go", "--brief", "nope"],
            {"ARGENTINE_CALLER_TOKEN": TOKEN},
            _unused_post,
        )
        self.assertEqual(code, 2)
        self.assertIn("not both", err)
        self.assertNotIn(TOKEN, out + err)

    def test_refuses_to_print_token_and_hides_transport_errors(self) -> None:
        def echo(_url, _token, _payload):
            return 200, {"decision": "GO", "fails": [TOKEN]}

        code, out, err = _run(["go"], {"ARGENTINE_CALLER_TOKEN": TOKEN}, echo)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertNotIn(TOKEN, err)
        self.assertIn("caller token", err)

        def broken(_url, _token, _payload):
            raise call_gate.CallError("gate request failed")

        code, out, err = _run(["go"], {"ARGENTINE_CALLER_TOKEN": TOKEN}, broken)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(err, "gate request failed\n")
        self.assertNotIn(TOKEN, err)

    def test_http_post_sends_bearer_and_drops_extra_fields(self) -> None:
        captured = {}

        class _Resp:
            status = 200

            def read(self) -> bytes:
                return b'{"decision":"GO","fails":[],"caller":"hidden"}'

            def __enter__(self):
                return self

            def __exit__(self, *args) -> bool:
                return False

        class _Opener:
            def open(self, req, timeout=None):
                captured["req"] = req
                captured["timeout"] = timeout
                return _Resp()

        status, body = call_gate.http_post(
            call_gate.DEFAULT_GATE_URL,
            TOKEN,
            _fixture("low-complete"),
            opener=_Opener(),
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["decision"], "GO")
        req = captured["req"]
        self.assertEqual(req.get_header("Authorization"), f"Bearer {TOKEN}")
        self.assertEqual(req.full_url, call_gate.DEFAULT_GATE_URL)
        self.assertEqual(json.loads(req.data.decode("utf-8")), _fixture("low-complete"))
        self.assertEqual(captured["timeout"], call_gate.TIMEOUT_S)
        opener = call_gate.build_opener()
        self.assertTrue(any(isinstance(handler, call_gate._NoRedirect) for handler in opener.handlers))

    def test_http_post_reads_error_json_and_hides_token(self) -> None:
        raw = b'{"decision":"NO_GO","fails":["unauthorized"]}'

        class _Opener:
            def open(self, req, timeout=None):
                raise urllib.error.HTTPError(
                    call_gate.DEFAULT_GATE_URL,
                    401,
                    "Unauthorized",
                    hdrs=None,
                    fp=io.BytesIO(raw),
                )

        status, body = call_gate.http_post("https://gate.example/v1/gate", TOKEN, {"brief": "x"}, opener=_Opener())
        self.assertEqual(status, 401)
        self.assertEqual(body, {"decision": "NO_GO", "fails": ["unauthorized"]})

        class _Down:
            def open(self, req, timeout=None):
                raise urllib.error.URLError(TOKEN)

        with self.assertRaises(call_gate.CallError) as caught:
            call_gate.http_post("https://gate.example/v1/gate", TOKEN, {"brief": "x"}, opener=_Down())
        self.assertNotIn(TOKEN, str(caught.exception))
        self.assertEqual(str(caught.exception), "gate request failed")

        class _Html:
            def open(self, req, timeout=None):
                raise urllib.error.HTTPError(
                    "https://gate.example/v1/gate",
                    502,
                    "Bad Gateway",
                    hdrs=None,
                    fp=io.BytesIO(f"<html>{TOKEN}</html>".encode()),
                )

        with self.assertRaises(call_gate.CallError) as caught:
            call_gate.http_post("https://gate.example/v1/gate", TOKEN, {"brief": "x"}, opener=_Html())
        self.assertEqual(str(caught.exception), "gate response was not JSON")
        self.assertNotIn(TOKEN, str(caught.exception))

    def test_local_server_smoke(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            env = {
                "ARGENTINE_CALLER_TOKEN": TOKEN,
                "ARGENTINE_GATE_URL": f"http://127.0.0.1:{port}/v1/gate",
            }
            code, out, err = _run(["need-human"], env, post=None)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(
            out,
            '{"decision":"NEED_HUMAN","fails":["hitl","approved_until","digest","kill_path"]}\n',
        )
        self.assertNotIn(TOKEN, out + err)
        captured = server.captured
        self.assertEqual(captured["path"], "/v1/gate")
        self.assertEqual(captured["authorization"], f"Bearer {TOKEN}")
        self.assertEqual(json.loads(captured["body"].decode("utf-8")), _fixture("high-missing"))

    def test_readme_caller_demo(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for phrase in (
            "## Caller demo",
            "ARGENTINE_CALLER_TOKEN",
            "ARGENTINE_GATE_URL",
            "https://argentine-a2a-production.up.railway.app/v1/gate",
            "python3 scripts/call_gate.py go",
            "python3 scripts/call_gate.py need-human",
        ):
            self.assertIn(phrase, readme)
        demo = readme.split("## Caller demo", 1)[1].split("## Request and response", 1)[0]
        self.assertNotIn("dev-diego", demo)
        self.assertNotIn("dev-ops", demo)
        allow = json.loads((ROOT / "config" / "allowlist.json").read_text(encoding="utf-8"))
        tokens = [caller["token"] for caller in allow["callers"]]
        self.assertEqual(tokens, ["dev-diego", "dev-ops"])
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("dev-diego", script)
        self.assertTrue(script.startswith("#!/usr/bin/env python3\n"))
        self.assertEqual(
            call_gate.DEFAULT_GATE_URL,
            "https://argentine-a2a-production.up.railway.app/v1/gate",
        )
        self.assertNotIn("fly.dev", script)


def _unused_post(url, token, payload):
    raise AssertionError("post should not run")


def _run(argv: list[str], env: dict, post) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = call_gate.main(argv, env=env, post=post)
    return code, stdout.getvalue(), stderr.getvalue()


if __name__ == "__main__":
    unittest.main()
