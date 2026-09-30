"""HTTP gate behavior: auth, rate limit, kill switch, concurrency, log, A2A."""

from __future__ import annotations

import json
import socket
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from http.client import HTTPConnection
from pathlib import Path

from argentine.auth import Allowlist
from argentine.killswitch import KillSwitch
from argentine.logstore import LOG_KEYS, JsonlLog, count_decisions
from argentine.server import GateApp, bind

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
TOKEN = "dev-diego"

GO_BODY = {
    "brief": (
        "digest: Read-only summary of local decisions for the caller.\n"
        "kill_path: Diego off-switch file var/diego.off\n"
        "side_effects: none\n"
    ),
    "blast_class": "low",
    "tools": [],
    "egress": ["reply"],
}


class GateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.log_path = self.root / "gate-log.jsonl"
        self.off = self.root / "diego.off"
        self.allow_path = self.root / "allowlist.json"
        self.allow_path.write_text(
            json.dumps(
                {
                    "callers": [
                        {"id": "diego", "token": "dev-diego"},
                        {"id": "ops", "token": "dev-ops"},
                    ]
                }
            ),
            encoding="utf-8",
        )

    def make_app(self, **kwargs) -> GateApp:
        env = kwargs.pop("env", None)
        rate_limit = kwargs.pop("rate_limit", 10)
        timeout_s = kwargs.pop("timeout_s", 15)
        decide_hook = kwargs.pop("decide_hook", None)
        max_concurrent = kwargs.pop("max_concurrent", 2)
        return GateApp(
            allowlist=Allowlist(path=self.allow_path),
            kill=KillSwitch(self.off, env=env),
            log=JsonlLog(self.log_path),
            now=lambda: NOW,
            timeout_s=timeout_s,
            max_concurrent=max_concurrent,
            rate_limit=rate_limit,
            decide_hook=decide_hook,
        )

    def post(self, app: GateApp, payload: dict, token: str = TOKEN, path: str = "/v1/gate"):
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        return app.handle("POST", path, headers, json.dumps(payload).encode("utf-8"))

    def test_go_response_is_only_decision_and_fails(self) -> None:
        status, body = self.post(self.make_app(), GO_BODY)
        self.assertEqual(status, 200)
        self.assertEqual(list(body.keys()), ["decision", "fails"])
        self.assertEqual(body, {"decision": "GO", "fails": []})

    def test_need_human_and_no_go(self) -> None:
        app = self.make_app()
        status, body = self.post(
            app,
            {
                "brief": "Review whether to draft a participation note.",
                "blast_class": "high",
                "tools": [],
                "egress": ["reply"],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["decision"], "NEED_HUMAN")
        self.assertEqual(body["fails"], ["hitl", "approved_until", "digest", "kill_path"])

        status, body = self.post(
            app,
            {
                "brief": (
                    "HITL: rejected\n"
                    "digest: Caller asked to post the draft and email subscribers.\n"
                    "kill_path: none\n"
                    "side_effects: post\n"
                ),
                "blast_class": "high",
                "tools": ["post"],
                "egress": ["moltbook"],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["decision"], "NO_GO")
        self.assertIn("hitl", body["fails"])
        self.assertIn("egress", body["fails"])

    def test_log_schema_hides_brief(self) -> None:
        sentinel = "UNIQUE_BRIEF_SENTINEL_do_not_log"
        payload = dict(GO_BODY)
        payload["brief"] = GO_BODY["brief"] + sentinel + "\n"
        # Digest must still pass; sentinel is an extra line, markers remain.
        app = self.make_app()
        status, body = self.post(app, payload)
        self.assertEqual(body["decision"], "GO")
        lines = self.log_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(list(record.keys()), list(LOG_KEYS))
        self.assertNotIn(sentinel, lines[0])
        self.assertTrue(record["brief_hash"].startswith("sha256:"))
        self.assertEqual(record["caller"], "diego")
        self.assertEqual(record["decision"], "GO")
        self.assertIs(record["human_reject"], False)
        self.assertEqual(record["blast_class"], "low")

    def test_human_reject_flag_and_stats(self) -> None:
        app = self.make_app()
        self.post(app, GO_BODY)
        self.post(app, {**GO_BODY, "human_reject": True, "brief": GO_BODY["brief"] + "HITL: approved\napproved_until: 2099-01-01T00:00:00Z\n"})
        status, stats = app.handle("GET", "/v1/gate/stats", {"Authorization": f"Bearer {TOKEN}"}, b"")
        self.assertEqual(status, 200)
        self.assertEqual(stats["human_reject"], 1)
        self.assertEqual(stats["decisions"], 2)
        self.assertEqual(stats["ratio"], "1/2")
        human, total = count_decisions(self.log_path)
        self.assertEqual((human, total), (1, 2))

    def test_unauthorized_and_allowlist_reload(self) -> None:
        app = self.make_app()
        status, body = self.post(app, GO_BODY, token="nope")
        self.assertEqual(status, 401)
        self.assertEqual(body, {"decision": "NO_GO", "fails": ["unauthorized"]})
        self.allow_path.write_text(
            json.dumps({"callers": [{"id": "diego", "token": "rotated"}]}),
            encoding="utf-8",
        )
        status, _body = self.post(app, GO_BODY, token="dev-diego")
        self.assertEqual(status, 401)
        status, body = self.post(app, GO_BODY, token="rotated")
        self.assertEqual(body["decision"], "GO")

    def test_rate_limit(self) -> None:
        app = self.make_app(rate_limit=2)
        self.assertEqual(self.post(app, GO_BODY)[1]["decision"], "GO")
        self.assertEqual(self.post(app, GO_BODY)[1]["decision"], "GO")
        status, body = self.post(app, GO_BODY)
        self.assertEqual(status, 429)
        self.assertEqual(body, {"decision": "NO_GO", "fails": ["rate_limited"]})

    def test_diego_off_file_and_env(self) -> None:
        app = self.make_app()
        self.assertEqual(self.post(app, GO_BODY)[1]["decision"], "GO")
        self.off.write_text("1", encoding="utf-8")
        status, body = self.post(app, GO_BODY)
        self.assertEqual(status, 503)
        self.assertEqual(body, {"decision": "NO_GO", "fails": ["diego_off"]})
        self.off.unlink()
        self.assertEqual(self.post(app, GO_BODY)[1]["decision"], "GO")

        shut = self.make_app(env={"ARGENTINE_DIEGO_OFF": "1"})
        status, body = self.post(shut, GO_BODY)
        self.assertEqual(status, 503)
        self.assertEqual(body["fails"], ["diego_off"])

    def test_timeout(self) -> None:
        def slow() -> None:
            time.sleep(0.15)

        app = self.make_app(timeout_s=0.05, decide_hook=slow)
        status, body = self.post(app, GO_BODY)
        self.assertEqual(status, 504)
        self.assertEqual(body, {"decision": "NO_GO", "fails": ["timeout"]})

    def test_concurrency_limit(self) -> None:
        hold = threading.Event()
        entered = threading.Semaphore(0)

        def hook() -> None:
            entered.release()
            hold.wait(timeout=2)

        app = self.make_app(max_concurrent=2, decide_hook=hook, timeout_s=5)
        results: list[tuple[int, dict]] = []
        lock = threading.Lock()

        def call() -> None:
            result = self.post(app, GO_BODY)
            with lock:
                results.append(result)

        threads = [threading.Thread(target=call) for _ in range(3)]
        for thread in threads:
            thread.start()
        self.assertTrue(entered.acquire(timeout=2))
        self.assertTrue(entered.acquire(timeout=2))
        deadline = time.time() + 2
        while time.time() < deadline:
            with lock:
                if any(body.get("fails") == ["concurrency_limit"] for _status, body in results):
                    break
            time.sleep(0.01)
        with lock:
            limited = [body for _status, body in results if body.get("fails") == ["concurrency_limit"]]
        self.assertEqual(len(limited), 1)
        hold.set()
        for thread in threads:
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())

    def test_a2a_message_send_ignores_callback_url(self) -> None:
        app = self.make_app()
        payload = {
            "jsonrpc": "2.0",
            "id": "rpc-1",
            "method": "message/send",
            "params": {
                "configuration": {"pushNotificationConfig": {"url": "http://127.0.0.1:9/nope"}},
                "message": {
                    "kind": "message",
                    "role": "user",
                    "messageId": "m1",
                    "parts": [
                        {"kind": "text", "text": GO_BODY["brief"]},
                        {
                            "kind": "data",
                            "data": {
                                "blast_class": "low",
                                "tools": [],
                                "egress": ["reply"],
                                "url": "http://127.0.0.1:9/also-nope",
                            },
                        },
                    ],
                },
            },
        }
        original = socket.create_connection

        def boom(*_args, **_kwargs):
            raise AssertionError("outbound socket")

        socket.create_connection = boom
        try:
            status, body = self.post(app, payload, path="/")
        finally:
            socket.create_connection = original
        self.assertEqual(status, 200)
        self.assertEqual(set(body.keys()), {"jsonrpc", "id", "result"})
        self.assertEqual(body["id"], "rpc-1")
        self.assertEqual(list(body["result"].keys()), ["decision", "fails"])
        self.assertEqual(body["result"], {"decision": "GO", "fails": []})

    def test_live_socket_on_loopback(self) -> None:
        app = self.make_app()
        httpd = bind(app, 0)
        self.assertEqual(httpd.server_address[0], "127.0.0.1")
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.shutdown)
        self.addCleanup(httpd.server_close)
        port = httpd.server_address[1]
        raw = json.dumps(GO_BODY).encode("utf-8")
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "POST",
            "/v1/gate",
            body=raw,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
                "Content-Length": str(len(raw)),
            },
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        conn.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(payload, {"decision": "GO", "fails": []})
        health = HTTPConnection("127.0.0.1", port, timeout=5)
        health.request("GET", "/health")
        health_body = json.loads(health.getresponse().read().decode("utf-8"))
        health.close()
        self.assertEqual(health_body["diego_off"], False)
        self.assertEqual(health_body["max_concurrent"], 2)
        self.assertEqual(health_body["timeout_seconds"], 15)

    def test_bind_all_interfaces_for_a_proxy(self) -> None:
        app = self.make_app()
        httpd = bind(app, 0, "0.0.0.0")
        self.assertEqual(httpd.server_address[0], "0.0.0.0")
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.shutdown)
        self.addCleanup(httpd.server_close)
        port = httpd.server_address[1]
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/health")
        body = json.loads(conn.getresponse().read().decode("utf-8"))
        conn.close()
        self.assertTrue(body["ok"])
        card = HTTPConnection("127.0.0.1", port, timeout=5)
        card.request("GET", "/.well-known/agent-card.json")
        served = json.loads(card.getresponse().read().decode("utf-8"))
        card.close()
        url = served["supportedInterfaces"][0]["url"]
        self.assertTrue(url.startswith("http://127.0.0.1:"))
        self.assertNotIn("fly.dev", url)

    def test_bind_refuses_other_addresses(self) -> None:
        with self.assertRaises(RuntimeError):
            bind(self.make_app(), 0, "192.168.1.9")

    def test_allowlist_env_overrides_file(self) -> None:
        allow = Allowlist(
            path=self.allow_path,
            env={
                "ARGENTINE_ALLOWLIST": json.dumps(
                    {"callers": [{"id": "ada", "token": "secret-token"}]}
                )
            },
        )
        app = self.make_app()
        app.allowlist = allow
        status, _body = self.post(app, GO_BODY, token="dev-diego")
        self.assertEqual(status, 401)
        status, body = self.post(app, GO_BODY, token="secret-token")
        self.assertEqual(body["decision"], "GO")
        self.assertEqual(json.loads(self.log_path.read_text().splitlines()[-1])["caller"], "ada")


if __name__ == "__main__":
    unittest.main()
