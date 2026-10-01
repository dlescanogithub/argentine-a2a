"""Railway is an alternate host. The public card stays on the Fly URL."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from argentine import ROOT

CARD_URL = "https://argentine-a2a.fly.dev"


class RailwayHostTest(unittest.TestCase):
    def test_config_is_iac_not_legacy_config_as_code(self) -> None:
        self.assertFalse((ROOT / "railway.toml").exists())
        self.assertFalse((ROOT / "railway.json").exists())
        text = (ROOT / ".railway" / "railway.ts").read_text(encoding="utf-8")
        for phrase in (
            'export const partial = "argentine-a2a"',
            'github("dlescanogithub/argentine-a2a"',
            'builder: "DOCKERFILE"',
            'dockerfilePath: "Dockerfile"',
            'healthcheck: "/health"',
            'replicas: 1',
            'requiredMountPath: "/data"',
            '"/data": gateLog',
            'volume("argentine_gate_log"',
            'sizeMB: 1024',
            'ARGENTINE_REQUIRE_ALLOWLIST_SECRET: "1"',
            'ARGENTINE_LOG_PATH: "/data/gate-log.jsonl"',
            'ARGENTINE_DIEGO_OFF_FILE: "/data/diego.off"',
            "ARGENTINE_ALLOWLIST: preserve()",
            "ARGENTINE_DIEGO_OFF: preserve()",
            'ARGENTINE_BIND: "0.0.0.0"',
        ):
            self.assertIn(phrase, text)
        self.assertNotIn("start:", text)
        self.assertNotIn("startCommand", text)
        self.assertNotIn("https://", text)
        self.assertNotIn("railway.app", text)
        self.assertNotIn(CARD_URL, text)
        for secret in ("dev-diego", "dev-ops", "REPLACE_DIEGO", "REPLACE_OPS"):
            self.assertNotIn(secret, text)

    def test_docs_keep_fly_and_describe_railway_cutover(self) -> None:
        ops = (ROOT / "docs" / "OPS.md").read_text(encoding="utf-8")
        railway = (ROOT / "docs" / "RAILWAY.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("https://argentine-a2a.fly.dev", ops)
        self.assertIn("fly secrets set", ops)
        self.assertIn("docs/RAILWAY.md", ops)
        self.assertIn("ARGENTINE_ALLOWLIST", ops)
        self.assertIn("ARGENTINE_REQUIRE_ALLOWLIST_SECRET=1", ops)
        self.assertIn("/data", ops)
        for phrase in (
            "Deploy from GitHub repo",
            "dlescanogithub/argentine-a2a",
            "mount path to `/data`",
            "/data/gate-log.jsonl",
            "/data/diego.off",
            "ARGENTINE_ALLOWLIST",
            "ARGENTINE_REQUIRE_ALLOWLIST_SECRET",
            "ARGENTINE_DIEGO_OFF",
            "GET /health",
            "/v1/gate/stats",
            "railway.toml",
            "railway.json",
            "2026-08-28",
            "https://<railway-hostname>/health",
            "agent-card.json",
            ".well-known/agent-card.json",
            "https://www.a2a-registry.org/agent/18978b04-ecd1-4283-8449-060c71014582",
            "Do not commit a placeholder hostname",
            "Leave `PORT` unset",
        ):
            self.assertIn(phrase, railway)
        self.assertNotIn("https://", railway.replace("https://argentine-a2a.fly.dev", "").replace(
            "https://<railway-hostname>",
            "",
        ).replace(
            "https://www.a2a-registry.org/agent/18978b04-ecd1-4283-8449-060c71014582",
            "",
        ))
        self.assertIn("docs/RAILWAY.md", readme)
        self.assertIn(CARD_URL, readme)
        card = (ROOT / "agent-card.json").read_text(encoding="utf-8")
        well_known = (ROOT / ".well-known" / "agent-card.json").read_text(encoding="utf-8")
        self.assertEqual(card, well_known)
        self.assertIn(CARD_URL, card)
        self.assertNotIn("railway", card.lower())

    def test_entrypoint_uses_port_when_set(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("root entrypoint drops to user gate before exec")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bindir = root / "bin"
            bindir.mkdir()
            fake = bindir / "python3"
            fake.write_text(
                f"#!{sys.executable}\n"
                "import os, sys\n"
                "print(os.environ.get('ARGENTINE_PORT', ''))\n"
                "print(' '.join(sys.argv))\n",
                encoding="utf-8",
            )
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

            def run(extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
                env = os.environ.copy()
                env.pop("PORT", None)
                env.pop("ARGENTINE_PORT", None)
                env["PATH"] = f"{bindir}{os.pathsep}{env.get('PATH', '')}"
                env["ARGENTINE_LOG_PATH"] = str(root / "data" / "gate-log.jsonl")
                env.update(extra)
                return subprocess.run(
                    [str(ROOT / "docker" / "entrypoint.sh")],
                    check=False,
                    capture_output=True,
                    text=True,
                    env=env,
                )

            kept = run({"ARGENTINE_PORT": "8080"})
            self.assertEqual(kept.returncode, 0, kept.stderr)
            self.assertEqual(kept.stdout.splitlines()[0], "8080")
            self.assertIn("python3 -m argentine serve", kept.stdout)

            mapped = run({"ARGENTINE_PORT": "8080", "PORT": "34567"})
            self.assertEqual(mapped.returncode, 0, mapped.stderr)
            self.assertEqual(mapped.stdout.splitlines()[0], "34567")

            unset = run({})
            self.assertEqual(unset.returncode, 0, unset.stderr)
            self.assertEqual(unset.stdout.splitlines()[0], "")

            for bad in ("0", "65536", "8080x", " "):
                failed = run({"PORT": bad})
                self.assertEqual(failed.returncode, 2, bad)
                self.assertIn("PORT must be an integer", failed.stderr)

    def test_fly_port_stays_8080(self) -> None:
        toml = (ROOT / "fly.toml").read_text(encoding="utf-8")
        docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn('ARGENTINE_PORT = "8080"', toml)
        self.assertIn("internal_port = 8080", toml)
        self.assertIn('path = "/health"', toml)
        self.assertIn('destination = "/data"', toml)
        without_argentine_port = toml.replace("ARGENTINE_PORT", "")
        self.assertNotIn("PORT =", without_argentine_port)
        self.assertIn("ARGENTINE_PORT=8080", docker)
        self.assertIn("EXPOSE 8080", docker)


if __name__ == "__main__":
    unittest.main()
