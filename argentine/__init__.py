"""ArGENTine A2A v1 local HITL/blast gate.

The process decides. It does not post, spend, execute caller tools, or call the network.
"""

from __future__ import annotations

from pathlib import Path

__version__ = "1.0.0"

ROOT = Path(__file__).resolve().parents[1]


def repo_root() -> Path:
    return ROOT
