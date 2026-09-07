"""Local update preferences and scheduling. Bootstrap remains the only updater."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any

import operations

READ_COMMANDS = frozenset({"context", "search", "resources", "resource-read", "browse", "review"})
INTERVAL = timedelta(hours=24)
RETRY_MINUTES = 5
RETRY_CAP_MINUTES = 360
AUTOMATIC_BUDGET = 10.0
POLICY_VERSION = 1


def timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def stamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def policy(runtime: dict) -> tuple[bool, str | None]:
    if not isinstance(runtime, dict):
        raise operations.OperationError("UPDATE_POLICY_INVALID", "The local runtime preferences are invalid.")
    enabled = runtime.get("automatic_updates", True)
    pinned = runtime.get("pinned_version")
    if not isinstance(enabled, bool) or (pinned is not None and (
        not isinstance(pinned, str) or not re.fullmatch(r"\d+\.\d+\.\d+", pinned)
    )):
        raise operations.OperationError("UPDATE_POLICY_INVALID", "Review the local update preferences before updating.")
    return enabled, pinned


def load_state(home: Path) -> dict:
    path = home / ".megabrain" / "update-state.json"
    if not path.exists():
        return {}
    try:
        state = json.loads(path.read_text())
        if not isinstance(state, dict):
            raise ValueError()
        return state
    except (OSError, ValueError) as error:
        raise operations.OperationError("UPDATE_STATE_INVALID", "Review the local update state before updating.") from error


def due(runtime: dict, state: dict, now: datetime) -> str | None:
    enabled, pinned = policy(runtime)
    if not enabled:
        return "automatic_updates_disabled"
    if pinned:
        return "version_pinned"
    checked = timestamp(state.get("checked_at"))
    next_check = timestamp(state.get("next_check_at"))
    # A backward clock jump must not freeze checks indefinitely.
    if checked and checked > now:
        return None
    if next_check is None and checked:
        interval = timedelta(minutes=RETRY_MINUTES) if state.get("status") in {"offline", "failed", "checking"} else INTERVAL
        next_check = checked + interval
    if next_check and now < next_check:
        return "retry_backoff" if state.get("status") in {"offline", "failed", "checking"} else "check_not_due"
    return None


def save_result(home: Path, result: dict, previous: dict, now: datetime) -> dict:
    failed = bool(result.get("stale"))
    failures = previous.get("failure_count", 0)
    failures = failures if isinstance(failures, int) and not isinstance(failures, bool) else 0
    failures = min(8, max(0, failures) + 1) if failed else 0
    delay = timedelta(minutes=min(RETRY_CAP_MINUTES, RETRY_MINUTES * 2 ** (failures - 1))) if failed else INTERVAL
    status = "failed" if failed else ("approval_required" if result.get("approval_required") else ("updated" if result.get("updated") else "current"))
    signature = previous.get("notice_signature")
    important = bool(result.get("updated") or result.get("approval_required"))
    new_signature = f"{status}:{result.get('latest_version', result.get('current_version'))}:{result.get('approval_reason', '')}"
    result["notify"] = important and signature != new_signature
    if result["notify"]:
        signature = new_signature
    if not result["notify"]:
        result.pop("notice", None)
    state = {
        "checked_at": stamp(now), "next_check_at": stamp(now + delay), "status": status,
        "failure_count": failures, "current_version": result.get("current_version"),
        "latest_version": result.get("latest_version"), "reason": result.get("reason"),
        "notice_signature": signature, "release_commit": result.get("release_commit"),
    }
    operations.atomic_write(home / ".megabrain" / "update-state.json", json.dumps(state, sort_keys=True) + "\n")
    return result
