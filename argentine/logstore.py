"""Local JSONL gate log. One object per line. The brief is stored only as a hash."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

LOG_KEYS = (
    "id",
    "ts",
    "caller",
    "brief_hash",
    "blast_class",
    "decision",
    "fails",
    "human_reject",
    "notes",
)


def brief_hash(brief: str) -> str:
    digest = hashlib.sha256(brief.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def format_ts(now: datetime) -> str:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc).replace(microsecond=0)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_record(
    *,
    caller: str,
    brief: str,
    blast_class: str | None,
    decision: str,
    fails: list[str],
    human_reject: bool,
    notes: str,
    now: datetime,
    record_id: str,
) -> dict:
    notes = " ".join(notes.split())
    record = {
        "id": record_id,
        "ts": format_ts(now),
        "caller": caller,
        "brief_hash": brief_hash(brief),
        "blast_class": blast_class,
        "decision": decision,
        "fails": list(fails),
        "human_reject": bool(human_reject),
        "notes": notes,
    }
    return {key: record[key] for key in LOG_KEYS}


class JsonlLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def append(self, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
        if "\n" in line or "\r" in line:
            raise ValueError("log record must be a single line")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()


def count_decisions(path: Path) -> tuple[int, int]:
    """Return (human_reject count, decision count)."""
    human = 0
    total = 0
    if not path.is_file():
        return 0, 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("decision") not in {"GO", "NO_GO", "NEED_HUMAN"}:
            continue
        total += 1
        if row.get("human_reject") is True:
            human += 1
    return human, total
