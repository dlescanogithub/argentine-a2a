"""Fixture loader and the checked-in sample gate log."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from argentine import ROOT
from argentine.logstore import build_record
from argentine.rubric import evaluate

BRIEFS_PATH = ROOT / "fixtures" / "briefs.json"
SAMPLE_LOG_PATH = ROOT / "fixtures" / "sample-gate-log.jsonl"

SAMPLE_ROWS = (
    ("11111111-1111-4111-8111-111111111111", "2026-09-30T12:00:00Z", "diego", "low-complete"),
    ("22222222-2222-4222-8222-222222222222", "2026-09-30T12:01:00Z", "diego", "high-complete"),
    ("33333333-3333-4333-8333-333333333333", "2026-09-30T12:02:00Z", "ops", "high-missing"),
    ("44444444-4444-4444-8444-444444444444", "2026-09-30T12:03:00Z", "diego", "high-reject"),
    ("55555555-5555-4555-8555-555555555555", "2026-09-30T12:04:00Z", "ops", "low-wide-egress"),
)


def parse_now(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_briefs(path=BRIEFS_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_request(request: dict, now: datetime):
    return evaluate(
        request["brief"],
        request["blast_class"] if "blast_class" in request else None,
        request["tools"] if "tools" in request else None,
        request["egress"] if "egress" in request else None,
        now=now,
        human_reject=request["human_reject"] if "human_reject" in request else None,
    )


def sample_records() -> list[dict]:
    payload = load_briefs()
    cases = {case["name"]: case for case in payload["cases"]}
    default_now = parse_now(payload.get("now") or "2026-09-30T12:00:00Z")
    rows: list[dict] = []
    for record_id, stamp, caller, name in SAMPLE_ROWS:
        case = cases[name]
        now = parse_now(case["now"]) if case.get("now") else default_now
        decision = evaluate_request(case["request"], now)
        rows.append(
            build_record(
                caller=caller,
                brief=case["request"]["brief"],
                blast_class=decision.blast_class,
                decision=decision.decision,
                fails=decision.fails,
                human_reject=decision.human_reject,
                notes=decision.notes,
                now=parse_now(stamp),
                record_id=record_id,
            )
        )
    return rows


def render_sample_log() -> str:
    lines = [
        json.dumps(row, ensure_ascii=True, separators=(",", ":"))
        for row in sample_records()
    ]
    return "\n".join(lines) + "\n"
