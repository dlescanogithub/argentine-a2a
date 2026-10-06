"""Diego off-switch.

The gate is shut when ARGENTINE_DIEGO_OFF is true or the flag file exists.
The file is checked on every request so `touch` (or the admin kill endpoint)
shuts the gate without a restart. The env var stays authoritative: clearing
the file does not open the gate while the env kill is on.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

_ON = {"1", "true", "yes", "on"}


class KillSwitch:
    def __init__(self, path: Path, env: Mapping[str, str] | None = None) -> None:
        self.path = path
        self._env = env

    def engaged(self) -> bool:
        return self.env_off() or self.file_off()

    def env_off(self) -> bool:
        env = self._env if self._env is not None else os.environ
        raw = str(env.get("ARGENTINE_DIEGO_OFF", "")).strip().lower()
        return raw in _ON

    def file_off(self) -> bool:
        try:
            return self.path.exists()
        except OSError:
            return True

    def engage_file(self) -> None:
        """Create the flag file (including parents). Empty file is enough."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def clear_file(self) -> None:
        """Remove the flag file if present. Env kill is unchanged."""
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            # Fail closed for reads; a stuck file on clear is reported by file_off().
            pass
