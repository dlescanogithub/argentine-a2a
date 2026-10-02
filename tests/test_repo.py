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

    def test_railway_evidence_pack_is_canonical_and_hashed(self) -> None:
        import hashlib

        pack = ROOT / "docs" / "evidence" / "2026-10-01-railway"
        lines = (pack / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        self.assertGreaterEqual(len(lines), 8)
        for line in lines:
            digest, name = line.split("  ", 1)
            self.assertEqual(hashlib.sha256((pack / name).read_bytes()).hexdigest(), digest, name)
        health = json.loads((pack / "health.json").read_text(encoding="utf-8"))
        self.assertEqual(health["ok"], True)
        self.assertEqual(health["diego_off"], True)
        card = json.loads((pack / "agent-card.live.json").read_text(encoding="utf-8"))
        self.assertEqual(card["version"], "1.2.0")
        self.assertEqual(
            card["supportedInterfaces"][0]["url"],
            "https://argentine-a2a-production.up.railway.app",
        )
        self.assertNotIn("fly.dev", json.dumps(card))
        partner = json.loads((pack / "partner-decisions.json").read_text(encoding="utf-8"))
        self.assertEqual(partner["caller_id"], "partner")
        self.assertEqual([case["decision"] for case in partner["cases"]], ["GO", "NEED_HUMAN"])
        summary = json.loads((pack / "SUMMARY.json").read_text(encoding="utf-8"))
        self.assertTrue(summary["canonical"])
        self.assertEqual(summary["exported_at_art"], "2026-10-01 21:01:12 ART")
        self.assertEqual(summary["partner_caller"]["ratio"], "0/11")
        self.assertEqual(summary["kill_path"]["flag_file"], "/data/diego.off")
        self.assertEqual(summary["kill_path"]["env"], "ARGENTINE_DIEGO_OFF")
        drill = summary["human_reject_drill"]
        self.assertEqual(drill["caller_id"], "partner")
        self.assertEqual(drill["ratio"], "1/28")
        self.assertEqual(drill["human_reject"], 1)
        self.assertEqual(drill["decisions"], 28)
        self.assertEqual(drill["decision"], "NO_GO")
        self.assertEqual(
            drill["fails"],
            ["hitl", "egress", "kill_path", "least_privilege", "side_effects"],
        )
        self.assertIs(drill["health_before_call"]["diego_off"], False)
        self.assertIs(drill["health_before_call"]["ok"], True)
        self.assertIs(drill["health_after"]["diego_off"], True)
        trace = json.loads((pack / "human-reject-2026-10-02.json").read_text(encoding="utf-8"))
        self.assertEqual(trace["caller_id"], "partner")
        self.assertEqual(trace["ts_utc"], "2026-10-02T00:48:56.560887+00:00")
        self.assertEqual(trace["stats_after_call"]["body"]["ratio"], "1/28")
        self.assertEqual(trace["health_after"]["body"]["diego_off"], True)
        self.assertEqual(trace["health_after"]["date_header"], "Fri, 02 Oct 2026 00:52:12 GMT")
        evidence = (ROOT / "docs" / "EVIDENCE.md").read_text(encoding="utf-8")
        self.assertIn("docs/evidence/2026-10-01-railway/", evidence)
        self.assertIn("historical Fly pack", evidence)
        self.assertIn("id `partner`", evidence)
        self.assertIn("`human_reject=1`, `decisions=28`, `ratio=1/28`", evidence)
        self.assertIn("`diego_off` restored true", evidence)
        blob = "\n".join(path.read_text(encoding="utf-8") for path in pack.iterdir())
        for secret in ("dev-diego", "dev-ops", "REPLACE_DIEGO", "REPLACE_OPS", "Authorization:"):
            self.assertNotIn(secret, blob)
        fly = ROOT / "docs" / "evidence" / "2026-10-01"
        for line in (fly / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            digest, name = line.split("  ", 1)
            self.assertEqual(hashlib.sha256((fly / name).read_bytes()).hexdigest(), digest, name)

    def test_homepage_points_at_the_live_gate(self) -> None:
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("https://argentine-a2a-production.up.railway.app", page)
        self.assertNotIn("fly.dev", page)
        self.assertIn("localhost", page)
        self.assertIn("not hosted on this page", page)


if __name__ == "__main__":
    unittest.main()
