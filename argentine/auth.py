"""Caller allowlist. Tokens are compared in constant time and never logged.

`ARGENTINE_ALLOWLIST` (a Fly secret or local env var) overrides the JSON file
when it is non-empty. The value is a JSON object: {"callers":[{"id","token"}]}.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path


class AllowlistError(Exception):
    pass


class Allowlist:
    def __init__(
        self,
        path: Path | None = None,
        callers: dict[str, str] | None = None,
        env=None,
    ) -> None:
        """callers maps token → caller id. A path or env value is re-read on every lookup."""
        self.path = path
        self._callers = callers
        self._env = env

    def check(self) -> None:
        self._load()

    def resolve(self, token: str) -> str | None:
        if not token:
            return None
        pairs = self._load()
        for caller_id, caller_token in pairs:
            try:
                match = secrets.compare_digest(token, caller_token)
            except (TypeError, ValueError):
                match = False
            if match:
                return caller_id
        return None

    def _load(self) -> list[tuple[str, str]]:
        if self._callers is not None:
            return [(caller_id, token) for token, caller_id in self._callers.items()]
        raw = self._allowlist_env()
        if raw is not None:
            try:
                data = json.loads(raw)
                rows = data["callers"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise AllowlistError("allowlist env is unreadable") from exc
            return _pairs(rows)
        if self.path is None or not self.path.is_file():
            raise AllowlistError("allowlist file is missing")
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            rows = data["callers"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise AllowlistError("allowlist file is unreadable") from exc
        return _pairs(rows)

    def _allowlist_env(self) -> str | None:
        env = os.environ if self._env is None else self._env
        if "ARGENTINE_ALLOWLIST" not in env:
            return None
        raw = str(env.get("ARGENTINE_ALLOWLIST", "")).strip()
        return raw or None


def _pairs(rows) -> list[tuple[str, str]]:
    if not isinstance(rows, list):
        raise AllowlistError("allowlist file is unreadable")
    pairs: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        caller_id = row.get("id")
        caller_token = row.get("token")
        if isinstance(caller_id, str) and caller_id and isinstance(caller_token, str) and caller_token:
            pairs.append((caller_id, caller_token))
    return pairs


def bearer_token(headers) -> str:
    raw = ""
    items = list(headers.items()) if hasattr(headers, "items") else []
    for key, value in items:
        if str(key).lower() == "authorization":
            raw = str(value)
            break
    scheme, _, token = raw.strip().partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return ""
    return token.strip()
