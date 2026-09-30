"""Deterministic checklist for a proposed action.

Each rubric item is PASS, FAIL, or MISSING.

- Any FAIL → NO_GO. A high-blast FAIL is a NO_GO, and so is any other
  definitive failure (rejected approval, expired TTL, egress outside the
  caller, disabled kill path, privilege, side effects, invalid blast class).
- No FAIL, but something required for a PASS is absent → NEED_HUMAN.
- Every item PASS → GO.

The checklist never calls a model and never invokes tools.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Mapping

Result = Literal["PASS", "FAIL", "MISSING"]

RUBRIC_ORDER: tuple[str, ...] = (
    "blast_class",
    "hitl",
    "approved_until",
    "digest",
    "egress",
    "kill_path",
    "least_privilege",
    "side_effects",
)

VALID_BLAST = {"low", "medium", "high"}
BLAST_RANK = {"low": 1, "medium": 2, "high": 3}

ALLOWED_EGRESS = {"reply", "caller", "reply_to_caller", "reply-to-caller"}

SAFE_TOOLS = {"none", "read", "read_brief", "read_log", "summarize", "draft", "checklist"}

PRIVILEGED_TOKENS = (
    "post",
    "publish",
    "moltbook",
    "mail",
    "email",
    "smtp",
    "spend",
    "pay",
    "transfer",
    "wallet",
    "execute",
    "exec",
    "shell",
    "bash",
    "delete",
    "drop",
    "write",
    "mutate",
    "send",
    "http",
    "https",
    "fetch",
    "browse",
    "webhook",
    "credential",
    "secret",
)

DISABLED_KILL = {"none", "no", "false", "off", "disabled", "removed", "unavailable"}
NO_SIDE_EFFECTS = {"none", "no", "false"}
REJECTED_HITL = {"rejected", "reject", "denied", "deny", "no", "false"}
APPROVED_HITL = {"approved", "approve", "yes", "true", "granted"}
DIGEST_MIN = 15

_MARKER = re.compile(
    r"^(hitl|human_approval|approved_by|approved_until|digest|kill_path|kill|abort|rollback|"
    r"side_effects|human_reject|blast_class|tools|egress)\s*:\s*(.*)$",
    re.IGNORECASE | re.MULTILINE,
)

_KILL_KEYS = ("kill_path", "kill", "abort", "rollback")


@dataclass(frozen=True)
class Decision:
    decision: str
    fails: list[str]
    human_reject: bool
    notes: str
    blast_class: str | None
    results: dict[str, Result]


def parse_markers(brief: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for match in _MARKER.finditer(brief or ""):
        found[match.group(1).lower()] = match.group(2).strip()
    return found


def split_list(value: str) -> list[str]:
    if not value.strip():
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _norm_blast(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip().lower()
    return text or None


def _tool_set(tools: list[str] | None) -> set[str]:
    if not tools:
        return set()
    return {tool.strip().lower() for tool in tools if tool.strip() and tool.strip().lower() != "none"}


def _egress_set(egress: list[str] | None) -> set[str]:
    if not egress:
        return set()
    return {item.strip().lower() for item in egress if item.strip()}


def _parse_time(value: str) -> datetime | None:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _approval_state(markers: Mapping[str, str], human_reject: bool | None) -> str:
    """Return rejected, approved, or absent."""
    if human_reject is True:
        return "rejected"
    flag = markers.get("human_reject")
    if flag is not None and flag.strip().lower() in {"1", "true", "yes", "rejected", "reject"}:
        return "rejected"
    hitl = markers.get("hitl", markers.get("human_approval"))
    if hitl is not None and hitl.strip():
        value = hitl.strip().lower()
        if value in REJECTED_HITL:
            return "rejected"
        if value in APPROVED_HITL:
            return "approved"
        return "absent"
    if markers.get("approved_by", "").strip():
        return "approved"
    return "absent"


def _effective_blast(field: str | None, marker: str | None) -> tuple[str | None, bool]:
    """Return the blast class used for later checks, and whether the claim conflicts or is invalid.

    Disagreeing claims fail closed: later checks use the more severe class.
    """
    norms = [_norm_blast(field), _norm_blast(marker)]
    present = [item for item in norms if item is not None]
    if not present:
        return None, False
    if len(present) == 2 and present[0] != present[1]:
        ranks = [BLAST_RANK.get(item, 3) for item in present]
        severe = max(ranks)
        name = {1: "low", 2: "medium", 3: "high"}[severe]
        return name, True
    claim = present[0]
    if claim not in VALID_BLAST:
        return "high", True
    return claim, False


def _is_privileged(tool: str) -> bool:
    name = tool.strip().lower()
    return any(token in name for token in PRIVILEGED_TOKENS)


def evaluate(
    brief: str,
    blast_class: str | None = None,
    tools: list[str] | None = None,
    egress: list[str] | None = None,
    *,
    now: datetime,
    human_reject: bool | None = None,
) -> Decision:
    if isinstance(blast_class, str) and not blast_class.strip():
        blast_class = None
    markers = parse_markers(brief)
    marker_blast = markers.get("blast_class") or None
    if marker_blast is not None and not marker_blast.strip():
        marker_blast = None
    effective, blast_bad = _effective_blast(blast_class, marker_blast)

    if tools is None and "tools" in markers:
        tools = split_list(markers["tools"])
    if egress is None and "egress" in markers:
        egress = split_list(markers["egress"])

    tools_conflict = False
    if tools is not None and "tools" in markers:
        if _tool_set(tools) != _tool_set(split_list(markers["tools"])):
            tools_conflict = True
    egress_conflict = False
    if egress is not None and "egress" in markers:
        if _egress_set(egress) != _egress_set(split_list(markers["egress"])):
            egress_conflict = True

    approval = _approval_state(markers, human_reject)
    results: dict[str, Result] = {}

    # 1. blast class present and valid, with no conflicting claim.
    if blast_class is None and marker_blast is None:
        results["blast_class"] = "MISSING"
    elif blast_bad:
        results["blast_class"] = "FAIL"
    else:
        results["blast_class"] = "PASS"

    # 2. HITL is required when the action is high-blast.
    if approval == "rejected":
        results["hitl"] = "FAIL"
    elif effective == "high":
        results["hitl"] = "PASS" if approval == "approved" else "MISSING"
    elif effective in {"low", "medium"}:
        results["hitl"] = "PASS"
    else:
        results["hitl"] = "PASS" if approval == "approved" else "MISSING"

    # 3. approved_until when the action is high-blast or an approval was claimed.
    ttl_applies = effective == "high" or approval in {"approved", "rejected"}
    ttl_raw = markers.get("approved_until")
    if not ttl_applies:
        results["approved_until"] = "PASS"
    elif ttl_raw is None or not ttl_raw.strip():
        results["approved_until"] = "MISSING"
    else:
        expires = _parse_time(ttl_raw)
        if expires is None:
            results["approved_until"] = "FAIL"
        else:
            current = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
            current = current.astimezone(timezone.utc)
            results["approved_until"] = "PASS" if expires > current else "FAIL"

    # 4. Digest of facts for the approver.
    digest = markers.get("digest", "")
    results["digest"] = "PASS" if len(digest.strip()) >= DIGEST_MIN else "MISSING"

    # 5. Egress scoped to the reply to the caller.
    if egress_conflict:
        results["egress"] = "FAIL"
    elif egress is None:
        results["egress"] = "MISSING"
    elif all(item.strip().lower() in ALLOWED_EGRESS for item in egress):
        results["egress"] = "PASS"
    else:
        results["egress"] = "FAIL"

    # 6. Kill path available on the proposed action.
    kill_value = None
    for key in _KILL_KEYS:
        if key in markers:
            kill_value = markers[key]
            break
    if kill_value is None:
        results["kill_path"] = "MISSING"
    elif not kill_value.strip() or kill_value.strip().lower() in DISABLED_KILL:
        results["kill_path"] = "FAIL" if kill_value.strip().lower() in DISABLED_KILL else "MISSING"
    else:
        results["kill_path"] = "PASS"

    # 7. Least privilege. Tools are classified and never executed.
    if tools_conflict:
        results["least_privilege"] = "FAIL"
    elif not tools:
        results["least_privilege"] = "PASS"
    else:
        privileged = False
        unknown = False
        for tool in tools:
            if not tool.strip() or tool.strip().lower() == "none":
                continue
            if _is_privileged(tool):
                privileged = True
            elif tool.strip().lower() not in SAFE_TOOLS:
                unknown = True
        if privileged:
            results["least_privilege"] = "FAIL"
        elif unknown:
            results["least_privilege"] = "MISSING"
        else:
            results["least_privilege"] = "PASS"

    # 8. No side effects in this call. Tools are never executed; a proposal
    # that asks this call to post, spend, or reach past the caller fails.
    side_text = markers.get("side_effects", "").strip().lower()
    declared_effect = bool(side_text) and side_text not in NO_SIDE_EFFECTS
    unsafe = results["egress"] == "FAIL" or results["least_privilege"] == "FAIL"
    results["side_effects"] = "FAIL" if declared_effect or unsafe else "PASS"

    fails = [item for item in RUBRIC_ORDER if results[item] != "PASS"]
    if any(results[item] == "FAIL" for item in RUBRIC_ORDER):
        decision = "NO_GO"
    elif fails:
        decision = "NEED_HUMAN"
    else:
        decision = "GO"

    notes = " ".join(f"{item}={results[item]}" for item in RUBRIC_ORDER)
    logged_blast = _norm_blast(blast_class if blast_class is not None else marker_blast)
    if logged_blast is not None:
        logged_blast = logged_blast[:64]

    return Decision(
        decision=decision,
        fails=fails,
        human_reject=approval == "rejected",
        notes=notes,
        blast_class=logged_blast,
        results=results,
    )
