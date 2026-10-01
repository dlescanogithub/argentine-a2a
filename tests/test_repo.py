"""Fixture decisions, sample log, and the no-egress constraint."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from argentine import ROOT
from argentine.__main__ import main
from argentine.logstore import LOG_KEYS, count_decisions
from argentine.samples import SAMPLE_LOG_PATH, load_briefs, render_sample_log, sample_records

BANNED = (
    "urllib.request",
    "urllib.error",
    "httpx",
    "requests",
    "smtplib",
    "socket.create_connection",
    "webbrowser",
)


class RepoTest(unittest.TestCase):
    def test_fixture_decisions(self) -> None:
        self.assertEqual(main(["decide"]), 0)

    def test_sample_log_matches_rubric_and_count(self) -> None:
        text = SAMPLE_LOG_PATH.read_text(encoding="utf-8")
        self.assertEqual(text, render_sample_log())
        rows = sample_records()
        self.assertEqual([row["decision"] for row in rows], ["GO", "GO", "NEED_HUMAN", "NO_GO", "NO_GO"])
        self.assertTrue(rows[3]["human_reject"])
        self.assertFalse(any(row["human_reject"] for row in rows if row is not rows[3]))
        for row in rows:
            self.assertEqual(list(row.keys()), list(LOG_KEYS))
        human, total = count_decisions(SAMPLE_LOG_PATH)
        self.assertEqual((human, total), (1, 5))
        from io import StringIO
        import contextlib

        buf = StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["count", "--log", str(SAMPLE_LOG_PATH)])
        self.assertEqual(code, 0)
        self.assertEqual(
            buf.getvalue().splitlines(),
            ["human_reject=1", "decisions=5", "ratio=1/5"],
        )

    def test_agent_cards_match_and_point_at_the_railway_gate(self) -> None:
        root_card = (ROOT / "agent-card.json").read_text(encoding="utf-8")
        well_known = (ROOT / ".well-known" / "agent-card.json").read_text(encoding="utf-8")
        self.assertEqual(root_card, well_known)
        card = json.loads(root_card)
        self.assertEqual(card["version"], "1.2.0")
        description = card["description"]
        self.assertIn("https://argentine-a2a-production.up.railway.app", description)
        self.assertIn("public A2A gate is live on Railway", description)
        self.assertNotIn("fly.dev", description)
        self.assertNotIn("live on Fly", description)
        self.assertIn("public URL is not the trust boundary", description)
        self.assertIn("remote Diego off-switch", description)
        self.assertIn("Not a general-purpose chatbot", description)
        self.assertIn("Does not impersonate Diego", description)
        self.assertIn("GO, NO_GO, or NEED_HUMAN", description)
        self.assertIn("allowlist Bearer", description)
        self.assertIn("ARGENTINE_DIEGO_OFF", description)
        self.assertIn("diego.off", description)
        self.assertNotIn("not publicly deployed", description)
        self.assertNotIn("localhost", description)
        self.assertEqual(
            card["provider"]["url"],
            "https://www.linkedin.com/in/diego-lescano-data-science",
        )
        skill_ids = [skill["id"] for skill in card["skills"]]
        self.assertEqual(skill_ids, ["hitl-blast-gate"])
        for interface in card["supportedInterfaces"]:
            self.assertEqual(interface["url"], "https://argentine-a2a-production.up.railway.app")
            self.assertEqual(interface["protocolBinding"], "JSONRPC")
            self.assertEqual(interface["protocolVersion"], "1.0")
            self.assertNotIn("127.0.0.1", interface["url"])

    def test_package_has_no_outbound_clients(self) -> None:
        package = ROOT / "argentine"
        for path in package.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for banned in BANNED:
                self.assertNotIn(banned, text, f"{path.name} imports {banned}")

    def test_readme_covers_run_off_switch_and_allowlist(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for phrase in (
            "python3 -m argentine serve",
            "127.0.0.1",
            "ARGENTINE_DIEGO_OFF",
            "diego.off",
            "config/allowlist.json",
            "ARGENTINE_RATE_LIMIT_PER_HOUR",
            "human_reject=1",
            "ratio=1/5",
            "docs/EVIDENCE.md",
            "public URL is not the trust boundary",
        ):
            self.assertIn(phrase, readme)
        evidence = (ROOT / "docs" / "EVIDENCE.md").read_text(encoding="utf-8")
        for phrase in (
            "public URL is not the trust boundary",
            "ARGENTINE_DIEGO_OFF",
            "diego.off",
            "/data/diego.off",
            "max_concurrent",
            "timeout_seconds",
            "GO",
            "NO_GO",
            "NEED_HUMAN",
            "human_reject",
            "https://argentine-a2a-production.up.railway.app/health",
            "Card version stays 1.2.0",
            "https://www.a2a-registry.org/agent/18978b04-ecd1-4283-8449-060c71014582",
            "github.dlescanogithub/argentine-a2a",
            "human_reject count",
            "2/16",
            "decisions=16",
            "2026-09-30 23:32 ART",
            "last kill-drill timestamp",
        ):
            self.assertIn(phrase, evidence)
        for secret in ("dev-diego", "dev-ops", "REPLACE_DIEGO", "REPLACE_OPS"):
            self.assertNotIn(secret, evidence)
        briefs = load_briefs()
        names = {case["name"] for case in briefs["cases"]}
        self.assertTrue({"low-complete", "high-missing", "high-reject"} <= names)

    def test_homepage_points_at_the_live_gate(self) -> None:
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("https://argentine-a2a-production.up.railway.app", page)
        self.assertNotIn("fly.dev", page)
        self.assertIn("localhost", page)
        self.assertIn("not hosted on this page", page)


if __name__ == "__main__":
    unittest.main()
