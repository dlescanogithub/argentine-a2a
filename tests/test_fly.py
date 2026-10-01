"""Fly hosting: bind flag, secrets, log rotation, and the public gate URL."""

from __future__ import annotations

import io
import json
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path

from argentine import ROOT
from argentine.__main__ import main
from argentine.auth import Allowlist, AllowlistError
from argentine.logstore import JsonlLog, build_record, count_decisions
from argentine.server import served_agent_card

CARD_URL = "https://argentine-a2a.fly.dev"
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


class FlyPrepTest(unittest.TestCase):
    def test_agent_card_points_at_the_fly_gate(self) -> None:
        for relative in ("agent-card.json", ".well-known/agent-card.json"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            card = json.loads(text)
            interface = card["supportedInterfaces"][0]
            self.assertEqual(interface["url"], CARD_URL)
            self.assertEqual(interface["protocolBinding"], "JSONRPC")
            self.assertEqual(interface["protocolVersion"], "1.0")
            self.assertNotIn("raw.githubusercontent.com", interface["url"])
            self.assertNotIn("0.0.0.0", text)
            self.assertNotIn("not publicly deployed", card["description"])
            self.assertNotIn("localhost", card["description"])
            self.assertEqual(card["version"], "1.2.0")
        served = served_agent_card(8080, "0.0.0.0")
        self.assertEqual(served["supportedInterfaces"][0]["url"], CARD_URL)
        self.assertNotIn("127.0.0.1", json.dumps(served["supportedInterfaces"]))
        self.assertIn("public URL is not the trust boundary", served["description"])
        loopback = served_agent_card(8787, "127.0.0.1")
        self.assertEqual(loopback["supportedInterfaces"][0]["url"], "http://127.0.0.1:8787/")
        self.assertEqual(loopback["description"], served["description"])

    def test_fly_artifacts_do_not_publish_a_url(self) -> None:
        toml = (ROOT / "fly.toml").read_text(encoding="utf-8")
        docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        entry = (ROOT / "docker" / "entrypoint.sh").read_text(encoding="utf-8")
        self.assertIn('ARGENTINE_BIND = "0.0.0.0"', toml)
        self.assertIn('source = "argentine_gate_log"', toml)
        self.assertIn('destination = "/data"', toml)
        self.assertIn("ARGENTINE_REQUIRE_ALLOWLIST_SECRET", toml)
        self.assertIn("/health", toml)
        self.assertNotIn("fly.dev", toml)
        self.assertNotIn("https://", toml)
        self.assertIn("ARGENTINE_BIND=0.0.0.0", docker)
        self.assertIn("8080", docker)
        self.assertNotIn("fly.dev", docker)
        self.assertIn("python3 -m argentine serve", entry)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for phrase in (
            "fly secrets set ARGENTINE_ALLOWLIST",
            "fly secrets set ARGENTINE_DIEGO_OFF",
            "Do not run `fly deploy`",
            "/data/diego.off",
            "ARGENTINE_STDOUT_LOG=1",
            "ARGENTINE_LOG_BACKUPS",
            "--bind 0.0.0.0",
        ):
            self.assertIn(phrase, readme)

    def test_missing_allowlist_secret_exits(self) -> None:
        keys = ("ARGENTINE_REQUIRE_ALLOWLIST_SECRET", "ARGENTINE_ALLOWLIST")
        saved = {key: os.environ.get(key) for key in keys}
        os.environ["ARGENTINE_REQUIRE_ALLOWLIST_SECRET"] = "1"
        os.environ.pop("ARGENTINE_ALLOWLIST", None)
        try:
            code = main(["serve", "--port", "9", "--bind", "127.0.0.1"])
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.assertEqual(code, 2)

    def test_blank_allowlist_env_uses_the_file(self) -> None:
        path = ROOT / "config" / "allowlist.json"
        allow = Allowlist(path=path, env={"ARGENTINE_ALLOWLIST": "  "})
        self.assertEqual(allow.resolve("dev-diego"), "diego")
        broken = Allowlist(path=path, env={"ARGENTINE_ALLOWLIST": "{"})
        with self.assertRaises(AllowlistError):
            broken.check()

    def test_log_rotates_and_mirrors_stdout(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "gate-log.jsonl"

            def record(index: int) -> dict:
                return build_record(
                    caller="diego",
                    brief=f"secret-brief-{index}-" + ("y" * 24),
                    blast_class="low",
                    decision="GO",
                    fails=[],
                    human_reject=False,
                    notes="rotated",
                    now=NOW,
                    record_id=f"00000000-0000-4000-8000-00000000000{index}",
                )

            line_size = len(json.dumps(record(0), ensure_ascii=True, separators=(",", ":")).encode("utf-8")) + 1
            mirror = io.StringIO()
            log = JsonlLog(path, max_bytes=line_size * 2, backups=1, stdout=True, stdout_stream=mirror)
            for index in range(5):
                log.append(record(index))
            self.assertTrue(path.is_file())
            self.assertTrue((root / "gate-log.jsonl.1").is_file())
            self.assertFalse((root / "gate-log.jsonl.2").exists())
            human, total = count_decisions(path)
            self.assertEqual(total, 3)
            self.assertEqual(human, 0)
            mirrored = mirror.getvalue().splitlines()
            self.assertEqual(len(mirrored), 5)
            self.assertNotIn("secret-brief", mirror.getvalue())
            self.assertTrue(mirrored[0].startswith("{"))


if __name__ == "__main__":
    unittest.main()
