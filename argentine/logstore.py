"""Local JSONL gate log. One object per line. The brief is stored only as a hash.

The durable copy is the file (on a Fly volume when hosted). An optional stdout
mirror writes the same line for the platform log collector. This module does
not open a network connection.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LOG_MAX_BYTES = 5_242_880
DEFAULT_LOG_BACKUPS = 3

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
    def __init__(
        self,
        path: Path,
        *,
        max_bytes: int = DEFAULT_LOG_MAX_BYTES,
        backups: int = DEFAULT_LOG_BACKUPS,
        stdout: bool = False,
        stdout_stream=None,
    ) -> None:
        self.path = path
        self.max_bytes = max_bytes
        self.backups = backups
        self.stdout = stdout
        self._stdout = stdout_stream if stdout_stream is not None else sys.stdout
        self._lock = threading.Lock()

    def append(self, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
        if "\n" in line or "\r" in line:
            raise ValueError("log record must be a single line")
        payload = line + "\n"
        encoded = payload.encode("utf-8")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._rotate_if_needed(len(encoded))
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if self.stdout:
                try:
                    self._stdout.write(payload)
                    self._stdout.flush()
                except OSError:
                    # The file is the durable copy. A broken stdout mirror
                    # must not drop the decision or open a network fallback.
                    pass

    def _rotate_if_needed(self, incoming: int) -> None:
        if self.backups < 1 or self.max_bytes < 1 or not self.path.is_file():
            return
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        if size == 0 or size + incoming <= self.max_bytes:
            return
        directory = self.path.parent
        name = self.path.name
        oldest = directory / f"{name}.{self.backups}"
        if oldest.exists():
            oldest.unlink()
        for index in range(self.backups - 1, 0, -1):
            src = directory / f"{name}.{index}"
            dst = directory / f"{name}.{index + 1}"
            if src.exists():
                src.replace(dst)
        self.path.replace(directory / f"{name}.1")


def decision_log_files(path: Path) -> list[Path]:
    """Active log plus rotated siblings `name.1`, `name.2`, ... until a gap."""
    files: list[Path] = []
    if path.is_file():
        files.append(path)
    index = 1
    while index <= 100:
        rotated = path.with_name(f"{path.name}.{index}")
        if not rotated.is_file():
            break
        files.append(rotated)
        index += 1
    return files


def count_decisions(path: Path) -> tuple[int, int]:
    """Return (human_reject count, decision count) across the active file and rotations."""
    human = 0
    total = 0
    for candidate in decision_log_files(path):
        for line in candidate.read_text(encoding="utf-8").splitlines():
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
