"""Shared, value-free agent activity for MegaBrain Home.

Each agent publishes its own lookup receipts to a separate branch of the owner's
private Brain repository, so Home can show how every agent uses MegaBrain. The
branch is a replaceable projection, never Brain knowledge or history:

- it holds identifiers, counts and times only, never message text;
- each agent writes only `activity/<its agent id>/`;
- every publish replaces the branch with one new commit, using
  `--force-with-lease` against the exact state it was built from (never plain
  force), so concurrent publishers retry instead of overwriting each other;
- receipts from other agents are untrusted data and are strictly validated.

Agents never download the branch for recall. Home and Live Home read it.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from types import ModuleType
from typing import Any, Iterable

import operations
import recall

BRANCH = "megabrain-activity"
REMOTE_REF = "refs/megabrain/activity/remote"
PUBLISH_INTERVAL_SECONDS = 1800
RETENTION_DAYS = 90
WINDOW_DAYS = 14
MAX_READ_BYTES = 8 * 1024 * 1024
MAX_LIST_ITEMS = 64
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
UUID_PATTERN = re.compile(UUID)
RESOURCE_PATTERN = re.compile(rf"megabrain://resource/{UUID}")
PATH_PATTERN = re.compile(rf"activity/({UUID})/(\d{{4}}-\d{{2}}-\d{{2}})\.jsonl")
EVENTS = {"session", "prompt", "search", "context"}
TRIGGERS = {"automatic", "agent"}
MODES = {"synced", "local", "offline", "unsynced"}
HARNESSES = {"codex", "claude", "hermes"}


def git(root: Path, *args: str, env: dict[str, str] | None = None, input: str | None = None) -> Any:
    return operations.run(["git", *args], root, env=env, input=input)


# --- Validation ------------------------------------------------------------


def valid_receipt(entry: Any) -> dict[str, Any] | None:
    """Return a normalized receipt, or None. Unknown fields are dropped, odd values reject the line."""
    if not isinstance(entry, dict) or entry.get("schema") != recall.ACTIVITY_SCHEMA:
        return None
    moment = recall.parse_stamp(entry.get("at"))
    memories = entry.get("memories", [])
    resources = entry.get("resources", [])
    conflicts = entry.get("conflicts", 0)
    duration = entry.get("duration_ms", 0)
    agent = entry.get("agent")
    if (
        moment is None
        or entry.get("event") not in EVENTS
        or entry.get("trigger") not in TRIGGERS
        or entry.get("mode", "local") not in MODES
        or (agent is not None and agent not in HARNESSES)
        or not isinstance(entry.get("found"), bool)
        or not isinstance(memories, list) or len(memories) > MAX_LIST_ITEMS
        or not all(isinstance(item, str) and UUID_PATTERN.fullmatch(item) for item in memories)
        or not isinstance(resources, list) or len(resources) > MAX_LIST_ITEMS
        or not all(
            isinstance(item, dict) and set(item) == {"uri", "revision_id"}
            and isinstance(item["uri"], str) and RESOURCE_PATTERN.fullmatch(item["uri"])
            and isinstance(item["revision_id"], str) and UUID_PATTERN.fullmatch(item["revision_id"])
            for item in resources
        )
        or not isinstance(conflicts, int) or isinstance(conflicts, bool) or not 0 <= conflicts <= 100
        or not isinstance(duration, int) or isinstance(duration, bool) or not 0 <= duration <= 3_600_000
    ):
        return None
    return {
        "schema": recall.ACTIVITY_SCHEMA, "at": recall.stamp(moment), "event": entry["event"],
        "trigger": entry["trigger"], "mode": entry.get("mode", "local"), "agent": agent,
        "found": entry["found"], "memories": memories, "resources": resources,
        "conflicts": conflicts, "duration_ms": duration,
    }


def parse_lines(text: str) -> list[dict[str, Any]]:
    receipts = []
    for line in text.splitlines():
        try:
            receipt = valid_receipt(json.loads(line))
        except ValueError:
            continue
        if receipt is not None:
            receipts.append(receipt)
    return receipts


# --- Publishing ------------------------------------------------------------


def fetch_remote(root: Path, timeout: float, ref: str = REMOTE_REF) -> str:
    """Fetch the shared activity branch into a private ref: fetched, missing or offline."""
    with operations.deadline(timeout):
        result = git(root, "fetch", "--no-tags", "--no-write-fetch-head", "origin", f"+refs/heads/{BRANCH}:{ref}")
    if result.returncode == 0:
        return "fetched"
    if "couldn't find remote ref" in (result.stderr or "").lower():
        git(root, "update-ref", "-d", ref)
        return "missing"
    return "offline"


def day_files(root: Path, now: datetime) -> dict[str, str]:
    """This agent's local receipts, validated and grouped into one file per UTC day."""
    grouped: dict[str, list[str]] = defaultdict(list)
    for entry in recall.read_activity(root, now - timedelta(days=RETENTION_DAYS)):
        receipt = valid_receipt({key: value for key, value in entry.items() if key != "_at"})
        if receipt is not None:
            grouped[receipt["at"][:10]].append(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return {day: "\n".join(lines) + "\n" for day, lines in sorted(grouped.items())}


def build_tree(root: Path, agent_id: str, files: dict[str, str], base: str | None) -> str:
    """Write a tree that replaces only this agent's directory, without touching the worktree or index."""
    state = root / ".megabrain"
    operations.private_directory(state)
    with tempfile.TemporaryDirectory(prefix="activity-", dir=state) as directory:
        work = Path(directory)
        env = {"GIT_INDEX_FILE": str(work / "index")}
        if git(root, "read-tree", *([base] if base else ["--empty"]), env=env).returncode:
            raise operations.OperationError("ACTIVITY_PUBLISH_FAILED", "The shared activity tree could not be read.")
        lines = []
        if base:
            listing = git(root, "ls-tree", "-r", "-z", "--name-only", base, "--", f"activity/{agent_id}/")
            lines.extend(f"0 {'0' * 40}\t{path}" for path in listing.stdout.split("\0") if path)
        paths = []
        for day, content in files.items():
            path = work / f"{day}.jsonl"
            path.write_text(content, encoding="utf-8")
            paths.append((day, path))
        if paths:
            hashed = git(root, "hash-object", "-w", "--stdin-paths", input="\n".join(str(path) for _, path in paths) + "\n")
            blobs = hashed.stdout.split()
            if hashed.returncode or len(blobs) != len(paths):
                raise operations.OperationError("ACTIVITY_PUBLISH_FAILED", "Activity receipts could not be stored.")
            lines.extend(f"100644 {blob}\tactivity/{agent_id}/{day}.jsonl" for (day, _), blob in zip(paths, blobs))
        if lines and git(root, "update-index", "--index-info", env=env, input="\n".join(lines) + "\n").returncode:
            raise operations.OperationError("ACTIVITY_PUBLISH_FAILED", "The shared activity tree could not be updated.")
        tree = git(root, "write-tree", env=env)
        if tree.returncode:
            raise operations.OperationError("ACTIVITY_PUBLISH_FAILED", "The shared activity tree could not be written.")
        return tree.stdout.strip()


def publish(mb: ModuleType, root: Path, *, timeout: float = 10.0, force: bool = False, now: datetime | None = None) -> dict[str, Any]:
    """Publish this agent's receipts at most every 30 minutes, and only when they changed."""
    moment = now or datetime.now(timezone.utc)
    try:
        agent_id = str(mb.load_identity(root).get("id"))
    except mb.BrainError:
        return {"published": False, "reason": "identity_missing"}
    if not UUID_PATTERN.fullmatch(agent_id):
        return {"published": False, "reason": "identity_missing"}
    files = day_files(root, moment)
    for content in files.values():
        if mb.detect_secret(content):  # Defensive: receipts are generated and validated, never free text.
            return {"published": False, "reason": "secret_rejected"}
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest()
    marker = root / ".megabrain" / "activity-publish.json"
    try:
        previous = json.loads(marker.read_text(encoding="utf-8")) if not marker.is_symlink() else {}
    except (OSError, ValueError):
        previous = {}
    last = recall.parse_stamp(previous.get("at")) if isinstance(previous, dict) else None
    if not force and isinstance(previous, dict) and previous.get("digest") == digest:
        return {"published": False, "reason": "unchanged"}
    if not force and last is not None and 0 <= (moment - last).total_seconds() < PUBLISH_INTERVAL_SECONDS:
        return {"published": False, "reason": "throttled"}
    for _ in range(3):
        status = fetch_remote(root, timeout)
        if status == "offline":
            return {"published": False, "reason": "remote_unavailable"}
        base = git(root, "rev-parse", "--verify", f"{REMOTE_REF}^{{commit}}").stdout.strip() if status == "fetched" else None
        tree = build_tree(root, agent_id, files, base)
        if base and git(root, "rev-parse", f"{base}^{{tree}}").stdout.strip() == tree:
            operations.atomic_write(marker, json.dumps({"at": recall.stamp(moment), "digest": digest}))
            return {"published": False, "reason": "already_current"}
        commit = git(root, "commit-tree", tree, "-m", f"activity: receipts for agent {agent_id}")
        if commit.returncode:
            return {"published": False, "reason": "commit_failed"}
        sha = commit.stdout.strip()
        with operations.deadline(timeout):
            pushed = git(root, "push", f"--force-with-lease=refs/heads/{BRANCH}:{base or ''}", "origin",
                         f"{sha}:refs/heads/{BRANCH}")
        if pushed.returncode == 0:
            git(root, "update-ref", REMOTE_REF, sha)
            operations.atomic_write(marker, json.dumps({"at": recall.stamp(moment), "digest": digest}))
            return {"published": True, "days": len(files)}
        # Another agent published first: rebuild from its state and try again.
    return {"published": False, "reason": "concurrent_updates"}


# --- Reading for Home ------------------------------------------------------


def remote_receipts(root: Path, since: datetime, *, exclude_agent: str | None, ref: str = REMOTE_REF) -> list[tuple[str, dict[str, Any]]]:
    if git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode:
        return []
    listing = git(root, "ls-tree", "-r", "-z", "-l", ref, "--", "activity/")
    wanted, total = [], 0
    for entry in listing.stdout.split("\0"):
        if not entry:
            continue
        header, _, path = entry.partition("\t")
        fields = header.split()
        match = PATH_PATTERN.fullmatch(path)
        if len(fields) != 4 or fields[1] != "blob" or not fields[3].isdigit() or not match:
            continue
        agent_id, day = match.groups()
        if agent_id == exclude_agent or day < f"{since:%Y-%m-%d}":
            continue
        total += int(fields[3])
        if total > MAX_READ_BYTES:
            break
        wanted.append((agent_id, fields[2]))
    if not wanted:
        return []
    read = operations.run(["git", "cat-file", "--batch"], root, text=False,
                          input="".join(f"{blob}\n" for _, blob in wanted).encode("ascii"))
    receipts: list[tuple[str, dict[str, Any]]] = []
    output, position = read.stdout if isinstance(read.stdout, bytes) else b"", 0
    for agent_id, _ in wanted:
        newline = output.find(b"\n", position)
        header = output[position:newline].split() if newline >= 0 else []
        if len(header) != 3 or not header[2].isdigit():
            break
        size = int(header[2])
        body = output[newline + 1:newline + 1 + size]
        position = newline + 1 + size + 1
        receipts.extend((agent_id, receipt) for receipt in parse_lines(body.decode("utf-8", "replace")))
    return receipts


def summary(
    receipts: Iterable[tuple[str, dict[str, Any]]],
    *,
    visible_ids: set[str],
    now: datetime | None = None,
    available: bool = True,
) -> dict[str, Any]:
    """Aggregate receipts for Home. Memory IDs outside the viewer's authorized set are never named."""
    moment = now or datetime.now(timezone.utc)
    week, day = moment - timedelta(days=7), moment - timedelta(days=1)
    per_agent: dict[str, dict[str, Any]] = {}
    daily: Counter[str] = Counter()
    daily_found: Counter[str] = Counter()
    uses: Counter[str] = Counter()
    totals = Counter()
    for agent_id, receipt in receipts:
        at = recall.parse_stamp(receipt["at"])
        if at is None or at > moment + timedelta(minutes=5):
            continue
        stats = per_agent.setdefault(agent_id, {
            "agent_id": agent_id, "harness": receipt.get("agent"), "last_used_at": None,
            "lookups_24h": 0, "lookups_7d": 0, "found_7d": 0, "automatic_7d": 0, "sessions_7d": 0,
        })
        stamp = recall.stamp(at)
        if stats["last_used_at"] is None or stamp > stats["last_used_at"]:
            stats["last_used_at"] = stamp
        lookup = receipt["event"] in recall.LOOKUP_EVENTS
        if lookup:
            daily[f"{at:%Y-%m-%d}"] += 1
            daily_found[f"{at:%Y-%m-%d}"] += int(receipt["found"])
        if at < week:
            continue
        if receipt["event"] == "session":
            stats["sessions_7d"] += 1
        if not lookup:
            continue
        stats["lookups_7d"] += 1
        stats["found_7d"] += int(receipt["found"])
        stats["automatic_7d"] += int(receipt["trigger"] == "automatic")
        stats["lookups_24h"] += int(at >= day)
        totals["lookups"] += 1
        totals["found"] += int(receipt["found"])
        for memory_id in receipt["memories"]:
            if memory_id in visible_ids:
                uses[memory_id] += 1
    days = [f"{moment - timedelta(days=offset):%Y-%m-%d}" for offset in range(WINDOW_DAYS - 1, -1, -1)]
    return {
        "available": available,
        "window_days": WINDOW_DAYS,
        "agents": sorted(per_agent.values(), key=lambda item: item["last_used_at"] or "", reverse=True),
        "totals_7d": {"lookups": totals["lookups"], "found": totals["found"], "nothing_found": totals["lookups"] - totals["found"]},
        "daily": [{"date": date, "lookups": daily[date], "found": daily_found[date]} for date in days],
        "top_memories": [{"id": memory_id, "uses": count} for memory_id, count in uses.most_common(5)],
    }


def home_activity(
    mb: ModuleType,
    root: Path,
    *,
    visible_ids: set[str],
    include_local: bool,
    ref: str = REMOTE_REF,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Activity for Home: other agents from the shared branch plus this clone's own latest receipts."""
    moment = now or datetime.now(timezone.utc)
    since = moment - timedelta(days=WINDOW_DAYS)
    local_agent = None
    if include_local:
        try:
            local_agent = str(mb.load_identity(root).get("id"))
        except mb.BrainError:
            local_agent = None
    receipts = remote_receipts(root, since, exclude_agent=local_agent, ref=ref)
    if local_agent:
        for entry in recall.read_activity(root, since):
            receipt = valid_receipt({key: value for key, value in entry.items() if key != "_at"})
            if receipt is not None:
                receipts.append((local_agent, receipt))
    shared = git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode == 0
    return summary(receipts, visible_ids=visible_ids, now=moment, available=bool(receipts) or shared)
