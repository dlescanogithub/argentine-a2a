"""Diego off-switch.

The gate is shut when ARGENTINE_DIEGO_OFF is true or the flag file exists.
The file is checked on every request so `touch` shuts the gate without a restart.
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
        env = self._env if self._env is not None else os.environ
        raw = str(env.get("ARGENTINE_DIEGO_OFF", "")).strip().lower()
        if raw in _ON:
            return True
        try:
            return self.path.exists()
        except OSError:
            return True
