#!/usr/bin/env python3
"""Dependency-free local-first Markdown memory helper."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
import webbrowser
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import vault as vault_module


MEMORY_SCHEMA = "megabrain.memory.v1"
AGENT_SCHEMA = "megabrain.agent.v1"
IMPORT_SCHEMA = "megabrain.import.v1"
BRAIN_SCHEMA = "megabrain.brain.v1"
RUNTIME_SCHEMA = "megabrain.runtime.v1"
SUPPORTED_PROTOCOL = 1
KINDS = {
    "fact",
    "preference",
    "decision",
    "commitment",
    "project-state",
    "resource",
    "correction",
    "tombstone",
}
CONFIDENCES = {"confirmed", "inferred", "unconfirmed"}
SENSITIVITIES = {"general", "private", "sensitive"}
IMPORTANCES = {"always", "core", "normal"}
ALWAYS_MEMORY_LIMIT = 3
CONFLICT_EXPANSION_LIMIT = 5
DEFAULT_FRESHNESS_SECONDS = 0
RETRIEVAL_INDEX_SCHEMA = "megabrain.retrieval-index.v2"
SOURCE_TYPES = {"user-statement", "agent-observation", "import"}
META_PATTERN = re.compile(
    r"\A<!--\s*megabrain-meta\s*\n(?P<meta>.*?)\n-->\s*\n(?P<body>.*)\Z",
    re.DOTALL,
)
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
TOKEN_STOPWORDS = {
    "a", "all", "an", "and", "are", "for", "in", "is", "it", "of", "on", "or",
    "should", "the", "this", "to", "use", "we", "what", "which", "with",
}
SHA256_PATTERN = re.compile(r"^(?:sha256:)?[a-f0-9]{64}$", re.I)
ROLE_LINE_PATTERN = re.compile(r"(?im)^(?:user|human|assistant|claude|codex|hermes)\s*:")
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore (?:all |any )?(?:previous|prior) instructions", re.I),
    re.compile(r"reveal (?:the )?system prompt", re.I),
    re.compile(r"execute (?:this|the following) command", re.I),
    re.compile(r"override (?:the )?(?:system|developer) message", re.I),
]
SECRET_PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.I)),
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")),
    (
        "labeled_secret",
        re.compile(
            r"\b(?:password|passwd|api[_ -]?key|access[_ -]?token|session[_ -]?cookie|recovery[_ -]?code)\s*[:=]\s*\S+",
            re.I,
        ),
    ),
    ("connection_string", re.compile(r"\b(?:postgres|mysql|mongodb(?:\+srv)?|redis)://[^\s/@:]+:[^\s/@]+@", re.I)),
]


class BrainError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class Record:
    path: Path
    meta: dict[str, Any]
    body: str


def semantic_version(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
    return tuple(map(int, match.groups())) if match else None


def runtime_manifest() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "runtime.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise BrainError("RUNTIME_INVALID", "MegaBrain runtime metadata is invalid") from error
    if (
        not isinstance(value, dict)
        or value.get("schema") != RUNTIME_SCHEMA
        or semantic_version(value.get("version")) is None
        or value.get("protocol_version") != SUPPORTED_PROTOCOL
    ):
        raise BrainError("RUNTIME_INVALID", "MegaBrain runtime metadata is invalid")
    return value


def brain_manifest(root: Path) -> dict[str, Any]:
    path = root / "megabrain.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise BrainError("BRAIN_MANIFEST_INVALID", "The brain compatibility manifest is invalid") from error
    if (
        not isinstance(value, dict)
        or value.get("schema") != BRAIN_SCHEMA
        or not isinstance(value.get("protocol_version"), int)
        or semantic_version(value.get("minimum_runtime")) is None
    ):
        raise BrainError("BRAIN_MANIFEST_INVALID", "The brain compatibility manifest is invalid")
    if "brain_id" in value and not valid_uuid(value.get("brain_id")):
        raise BrainError("BRAIN_MANIFEST_INVALID", "The brain identifier is invalid")
    return value


def require_compatible_runtime(root: Path, *, writing: bool) -> dict[str, Any]:
    brain = brain_manifest(root)
    runtime = runtime_manifest()
    if brain["protocol_version"] > runtime["protocol_version"]:
        raise BrainError(
            "PROTOCOL_UPDATE_REQUIRED",
            "This brain requires a newer MegaBrain protocol",
            {"brain_protocol": brain["protocol_version"], "runtime_protocol": runtime["protocol_version"]},
        )
    if writing and semantic_version(runtime["version"]) < semantic_version(brain["minimum_runtime"]):
        raise BrainError(
            "RUNTIME_UPDATE_REQUIRED",
            "Update MegaBrain before writing to this brain",
            {"minimum_runtime": brain["minimum_runtime"], "runtime_version": runtime["version"]},
        )
    return {"brain": brain, "runtime": runtime}


def runtime_can_write(compatibility: dict[str, Any]) -> bool:
    return semantic_version(compatibility["runtime"]["version"]) >= semantic_version(
        compatibility["brain"]["minimum_runtime"]
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def repo_root() -> Path:
    override = os.environ.get("MEGABRAIN_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    invoked = Path(os.path.abspath(__file__))
    harness = next((name for name in ("codex", "claude", "hermes") if f".{name}" in invoked.parts), None)
    config = Path.home() / ".megabrain" / "config.json"
    if harness and config.exists():
        try:
            value = json.loads(config.read_text(encoding="utf-8"))
            clone = value.get("clones", {}).get(harness) if isinstance(value, dict) else None
            if clone:
                root = Path(str(clone)).expanduser().resolve()
                if (root / "brain").is_dir():
                    return root
        except (json.JSONDecodeError, OSError):
            pass
    candidate = Path(__file__).resolve().parents[3]
    if (candidate / "brain").is_dir():
        return candidate
    raise BrainError("SETUP_REQUIRED", "MegaBrain has not been set up for this agent yet")


def emit(payload: dict[str, Any], *, stream: Any = sys.stdout) -> None:
    json.dump(payload, stream, ensure_ascii=True, sort_keys=True, indent=2)
    stream.write("\n")


def read_input(required: bool = True) -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        if required:
            raise BrainError("INPUT_REQUIRED", "Expected a JSON object on stdin")
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise BrainError("INVALID_JSON", "Input must be valid JSON", {"line": error.lineno}) from error
    if not isinstance(value, dict):
        raise BrainError("INVALID_INPUT", "Input must be a JSON object")
    return value


def parse_record(path: Path) -> Record:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise BrainError("INVALID_ENCODING", "Record is not UTF-8", {"path": str(path)}) from error
    match = META_PATTERN.match(text)
    if not match:
        raise BrainError("INVALID_RECORD", "Missing megabrain-meta block", {"path": str(path)})
    try:
        meta = json.loads(match.group("meta"))
    except json.JSONDecodeError as error:
        raise BrainError("INVALID_METADATA", "Metadata block is not valid JSON", {"path": str(path)}) from error
    if not isinstance(meta, dict):
        raise BrainError("INVALID_METADATA", "Metadata must be a JSON object", {"path": str(path)})
    return Record(path=path, meta=meta, body=match.group("body").strip())


def write_record(path: Path, meta: dict[str, Any], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = json.dumps(meta, ensure_ascii=True, sort_keys=True, indent=2)
    path.write_text(f"<!-- megabrain-meta\n{metadata}\n-->\n\n{body.strip()}\n", encoding="utf-8")


def valid_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def validate_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value.endswith("Z")
    except ValueError:
        return False


def validate_memory(record: Record) -> list[str]:
    meta = record.meta
    errors: list[str] = []
    required = {
        "schema",
        "id",
        "kind",
        "subject",
        "created_at",
        "created_by",
        "confidence",
        "sensitivity",
        "importance",
        "tags",
        "supersedes",
        "source",
    }
    missing = sorted(required - set(meta))
    if missing:
        errors.append(f"missing fields: {', '.join(missing)}")
    if meta.get("schema") != MEMORY_SCHEMA:
        errors.append("invalid schema")
    if not valid_uuid(meta.get("id")):
        errors.append("id must be a UUID")
    if meta.get("kind") not in KINDS:
        errors.append("invalid kind")
    if not isinstance(meta.get("subject"), str) or not meta.get("subject", "").strip():
        errors.append("subject must be a non-empty string")
    if not validate_timestamp(meta.get("created_at")):
        errors.append("created_at must be a UTC ISO timestamp")
    if not valid_uuid(meta.get("created_by")):
        errors.append("created_by must be an agent UUID")
    if meta.get("confidence") not in CONFIDENCES:
        errors.append("invalid confidence")
    if meta.get("sensitivity") not in SENSITIVITIES:
        errors.append("invalid sensitivity")
    if meta.get("importance") not in IMPORTANCES:
        errors.append("invalid importance")
    if not isinstance(meta.get("tags"), list) or not all(isinstance(tag, str) and tag.strip() for tag in meta.get("tags", [])):
        errors.append("tags must be non-empty strings")
    supersedes = meta.get("supersedes")
    if not isinstance(supersedes, list) or not all(valid_uuid(item) for item in supersedes):
        errors.append("supersedes must contain UUIDs")
    if meta.get("kind") in {"correction", "tombstone"} and not supersedes:
        errors.append("corrections and tombstones must supersede an earlier memory")
    if isinstance(supersedes, list) and meta.get("id") in supersedes:
        errors.append("a memory cannot supersede itself")
    source = meta.get("source")
    if not isinstance(source, dict) or source.get("type") not in SOURCE_TYPES:
        errors.append("source.type is invalid")
    else:
        for field in ("locator", "hash", "import_batch"):
            if field in source and source[field] is not None and not isinstance(source[field], str):
                errors.append(f"source.{field} must be a string or null")
        if source.get("hash") and not SHA256_PATTERN.fullmatch(str(source["hash"])):
            errors.append("source.hash must be a SHA-256 fingerprint")
    if not record.body:
        errors.append("memory body is empty")
    if len(ROLE_LINE_PATTERN.findall(record.body)) >= 2:
        errors.append("raw transcript-like content is forbidden")
    secret = detect_secret({"meta": meta, "body": record.body})
    if secret:
        errors.append(f"possible secret material: {secret}")
    if isinstance(source, dict) and source.get("type") == "import" and contains_prompt_injection({"meta": meta, "body": record.body}):
        errors.append("instruction-like imported content is forbidden")
    return errors


def validate_agent(record: Record) -> list[str]:
    meta = record.meta
    errors: list[str] = []
    if meta.get("schema") != AGENT_SCHEMA:
        errors.append("invalid schema")
    if not valid_uuid(meta.get("id")):
        errors.append("id must be a UUID")
    if meta.get("harness") not in {"codex", "claude", "hermes"}:
        errors.append("invalid harness")
    if not isinstance(meta.get("display_name"), str) or not meta.get("display_name", "").strip():
        errors.append("display_name is required")
    if not validate_timestamp(meta.get("created_at")):
        errors.append("created_at must be a UTC ISO timestamp")
    secret = detect_secret({"meta": meta, "body": record.body})
    if secret:
        errors.append(f"possible secret material: {secret}")
    return errors


def validate_import(record: Record) -> list[str]:
    meta = record.meta
    errors: list[str] = []
    if meta.get("schema") != IMPORT_SCHEMA:
        errors.append("invalid schema")
    if not valid_uuid(meta.get("id")):
        errors.append("id must be a UUID")
    if not valid_uuid(meta.get("created_by")):
        errors.append("created_by must be an agent UUID")
    if not validate_timestamp(meta.get("created_at")):
        errors.append("created_at must be a UTC ISO timestamp")
    source = meta.get("source")
    if not isinstance(source, dict) or not all(isinstance(source.get(key), str) and source[key] for key in ("type", "locator", "hash")):
        errors.append("source type, locator, and hash are required")
    counts = meta.get("counts")
    if not isinstance(counts, dict) or not all(isinstance(value, int) and value >= 0 for value in (counts or {}).values()):
        errors.append("counts must contain non-negative integers")
    coverage = meta.get("coverage", [])
    if not isinstance(coverage, list):
        errors.append("coverage must be an array")
    else:
        for entry in coverage:
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("locator"), str)
                or entry.get("access") not in {"writable", "reference-only", "excluded"}
                or entry.get("status") not in {"discovered", "scanned", "candidate-extracted", "intentionally-skipped"}
                or not isinstance(entry.get("canonical"), bool)
            ):
                errors.append("coverage entries must declare locator, access, canonical, and status")
    secret = detect_secret({"meta": meta, "body": record.body})
    if secret:
        errors.append(f"possible secret material: {secret}")
    return errors


def strings_in(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from strings_in(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from strings_in(item)


def detect_secret(value: Any) -> str | None:
    for text in strings_in(value):
        for name, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                return name
    return None


def contains_prompt_injection(value: Any) -> bool:
    return any(pattern.search(text) for text in strings_in(value) for pattern in PROMPT_INJECTION_PATTERNS)


def memory_files(root: Path) -> list[Path]:
    return sorted((root / "brain" / "memories").glob("*/*/*.md"))


def agent_files(root: Path) -> list[Path]:
    return sorted((root / "brain" / "agents").glob("*.md"))


def import_files(root: Path) -> list[Path]:
    return sorted((root / "brain" / "imports").glob("*.md"))


def load_records(paths: Iterable[Path]) -> list[Record]:
    return [parse_record(path) for path in paths]


def load_memories(root: Path) -> list[Record]:
    return load_records(memory_files(root))


def current_memories(records: list[Record]) -> tuple[list[Record], dict[str, list[str]]]:
    superseded = {
        memory_id
        for record in records
        for memory_id in (
            record.meta.get("supersedes", []) if isinstance(record.meta.get("supersedes", []), list) else []
        )
        if isinstance(memory_id, str)
    }
    active = [
        record
        for record in records
        if record.meta.get("id") not in superseded and record.meta.get("kind") != "tombstone"
    ]
    by_subject: dict[str, list[Record]] = defaultdict(list)
    for record in active:
        by_subject[normalize(record.meta.get("subject", ""))].append(record)
    conflicts: dict[str, list[str]] = {}
    for subject, subject_records in by_subject.items():
        summaries = {normalize(summary_text(record)) for record in subject_records}
        if len(summaries) > 1:
            conflicts[subject] = [str(record.meta["id"]) for record in subject_records]
    return active, conflicts


def summary_text(record: Record) -> str:
    lines = [line.strip() for line in record.body.splitlines() if line.strip()]
    if lines and lines[0].startswith("#"):
        lines = lines[1:]
    return "\n".join(lines).strip()


def normalize(value: str) -> str:
    return " ".join(TOKEN_PATTERN.findall(value.lower()))


def tokens(value: str) -> set[str]:
    raw = TOKEN_PATTERN.findall(value.lower())
    result = set(raw)
    for token in raw:
        result.update(TOKEN_PATTERN.findall(re.sub(r"(?<=[a-z])(?=[0-9])|(?<=[0-9])(?=[a-z])", " ", token)))
        if len(token) > 3 and token.endswith("s"):
            result.add(token[:-1])
    return {token for token in result if token not in TOKEN_STOPWORDS and not token.isdigit()}


def score_memory(record: Record, task_tokens: set[str]) -> int:
    meta = record.meta
    subject_tokens = tokens(str(meta.get("subject", "")))
    tag_tokens = tokens(" ".join(str(tag) for tag in meta.get("tags", [])))
    body_tokens = tokens(summary_text(record))
    return 6 * len(task_tokens & subject_tokens) + 4 * len(task_tokens & tag_tokens) + len(task_tokens & body_tokens)


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def git_commit(root: Path) -> str | None:
    result = run(["git", "rev-parse", "HEAD"], root)
    return result.stdout.strip() if result.returncode == 0 else None


def sync_state_path(root: Path) -> Path:
    return root / ".megabrain" / "sync-state.json"


def recent_sync(root: Path, freshness_seconds: int) -> dict[str, Any] | None:
    try:
        state = json.loads(sync_state_path(root).read_text(encoding="utf-8"))
        age = time.time() - float(state["successful_at"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
    if state.get("commit") != git_commit(root) or not 0 <= age <= freshness_seconds:
        return None
    return {
        "synced": True,
        "stale": False,
        "reason": "freshness_window",
        "pending_local_commits": False,
        "freshness_age_seconds": round(age, 3),
        "freshness_window_seconds": freshness_seconds,
    }


def sync_marker(root: Path) -> float | None:
    try:
        state = json.loads(sync_state_path(root).read_text(encoding="utf-8"))
        if state.get("commit") != git_commit(root):
            return None
        return float(state["successful_at"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def remember_sync(root: Path) -> None:
    commit = git_commit(root)
    if commit:
        atomic_json(sync_state_path(root), {"commit": commit, "successful_at": time.time()})


def relative(root: Path, path: Path) -> str:
    return str(path.relative_to(root))


def run(command: list[str], cwd: Path, *, check: bool = False) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if check and completed.returncode != 0:
        raise BrainError(
            "COMMAND_FAILED",
            f"Command failed: {command[0]}",
            {"returncode": completed.returncode, "stderr": safe_git_error(completed.stderr)},
        )
    return completed


def safe_git_error(value: str) -> str:
    sanitized = re.sub(r"(https?://)[^/@\s]+@", r"\1[credentials]@", value)
    return sanitized.strip()[-500:]


def is_git_repo(root: Path) -> bool:
    return run(["git", "rev-parse", "--is-inside-work-tree"], root).stdout.strip() == "true"


def changed_files(root: Path) -> list[str]:
    result = run(["git", "status", "--porcelain", "--untracked-files=all"], root)
    if result.returncode != 0:
        return ["<git status failed>"]
    return [line[3:] for line in result.stdout.splitlines() if line.strip()]


def has_remote(root: Path) -> bool:
    return run(["git", "remote", "get-url", "origin"], root).returncode == 0


def rebase_remote(root: Path) -> tuple[bool, str | None]:
    fetched = run(["git", "fetch", "origin", "main"], root)
    if fetched.returncode != 0:
        return False, "remote_unavailable"
    rebased = run(["git", "rebase", "origin/main"], root)
    if rebased.returncode != 0:
        run(["git", "rebase", "--abort"], root)
        return False, "rebase_conflict"
    return True, None


def push_with_retry(root: Path, attempts: int = 3) -> tuple[bool, str | None]:
    for _ in range(attempts):
        pushed = run(["git", "push", "origin", "HEAD:main"], root)
        if pushed.returncode == 0:
            return True, None
        rebased, reason = rebase_remote(root)
        if not rebased:
            return False, reason
    return False, "push_rejected"


def sync_repo(
    root: Path,
    *,
    allow_push: bool = True,
    fresh: bool = True,
    freshness_seconds: int = DEFAULT_FRESHNESS_SECONDS,
) -> dict[str, Any]:
    if not is_git_repo(root):
        return {"synced": False, "stale": True, "reason": "not_a_git_repository"}
    dirty = changed_files(root)
    if dirty:
        return {"synced": False, "stale": True, "reason": "dirty_worktree", "files": dirty}
    if not has_remote(root):
        return {"synced": False, "stale": True, "reason": "missing_origin"}
    observed_sync = sync_marker(root) if not fresh else None
    if not fresh and freshness_seconds > 0:
        cached = recent_sync(root, freshness_seconds)
        if cached:
            return cached
    lock_path = root / ".megabrain" / "sync.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with lock_path.open("a+", encoding="utf-8") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not fresh and freshness_seconds > 0:
            cached = recent_sync(root, freshness_seconds)
            if cached:
                return cached
        if not fresh:
            completed_while_waiting = sync_marker(root)
            if completed_while_waiting is not None and (
                observed_sync is None or completed_while_waiting > observed_sync
            ):
                return {
                    "synced": True,
                    "stale": False,
                    "reason": "coalesced",
                    "pending_local_commits": False,
                    "freshness_window_seconds": 0,
                }
        rebased, reason = rebase_remote(root)
        if not rebased:
            if reason == "remote_unavailable":
                validation = command_validate(root)
                if not validation["ok"]:
                    return {
                        "synced": False,
                        "stale": True,
                        "reason": "validation_failed",
                        "error_count": len(validation["errors"]),
                    }
            return {"synced": False, "stale": True, "reason": reason}
        validation = command_validate(root)
        if not validation["ok"]:
            return {
                "synced": False,
                "stale": True,
                "reason": "validation_failed",
                "error_count": len(validation["errors"]),
            }
        if not allow_push:
            ahead = run(["git", "rev-list", "--count", "origin/main..HEAD"], root)
            pending = ahead.returncode != 0 or ahead.stdout.strip() != "0"
            result = {
                "synced": not pending,
                "stale": pending,
                "reason": "runtime_update_required" if pending else None,
                "pending_local_commits": pending,
            }
            if not pending:
                remember_sync(root)
            return result
        pushed, reason = push_with_retry(root)
        if not pushed:
            return {"synced": False, "stale": True, "reason": reason, "pending_local_commits": True}
        remember_sync(root)
        return {"synced": True, "stale": False, "reason": None, "pending_local_commits": False}


def require_clean_or_offline(sync: dict[str, Any]) -> None:
    if sync.get("reason") in {
        "dirty_worktree",
        "rebase_conflict",
        "not_a_git_repository",
        "missing_origin",
        "validation_failed",
    }:
        raise BrainError("SYNC_BLOCKED", "Cannot write until the managed clone is healthy", sync)


def local_config_path(root: Path) -> Path:
    return root / ".megabrain" / "local.json"


def load_identity(root: Path) -> dict[str, Any]:
    path = local_config_path(root)
    if not path.exists():
        raise BrainError("AGENT_NOT_INSTALLED", "Run install.py for this agent environment first")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise BrainError("INVALID_AGENT_IDENTITY", "Local agent identity is invalid") from error
    if not isinstance(value, dict) or not valid_uuid(value.get("id")):
        raise BrainError("INVALID_AGENT_IDENTITY", "Local agent identity is invalid")
    return value


def source_from_input(value: Any, default_type: str) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    source_type = source.get("type", default_type)
    if source_type not in SOURCE_TYPES:
        raise BrainError("INVALID_SOURCE", "source.type is invalid")
    result: dict[str, Any] = {"type": source_type}
    for field in ("locator", "hash", "import_batch"):
        field_value = source.get(field)
        if field_value is not None:
            if not isinstance(field_value, str):
                raise BrainError("INVALID_SOURCE", f"source.{field} must be a string")
            result[field] = field_value
    return result


def validate_candidate(payload: dict[str, Any], *, importing: bool = False) -> None:
    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise BrainError("INVALID_SUMMARY", "summary must be a non-empty string")
    if len(summary) > 8_000:
        raise BrainError("SUMMARY_TOO_LONG", "summary must be at most 8000 characters")
    if len(ROLE_LINE_PATTERN.findall(summary)) >= 2:
        raise BrainError("RAW_TRANSCRIPT_REJECTED", "Raw transcript-like content cannot be stored")
    secret = detect_secret(payload)
    if secret:
        raise BrainError("SECRET_VALUE_REJECTED", "Likely secret material cannot be stored", {"classification": secret})
    if importing and contains_prompt_injection(payload):
        raise BrainError("UNTRUSTED_INSTRUCTION_REJECTED", "Instruction-like imported content cannot become memory")


def memory_meta(
    payload: dict[str, Any],
    identity: dict[str, Any],
    *,
    memory_id: str,
    kind: str | None = None,
    subject: str | None = None,
    supersedes: list[str] | None = None,
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected_kind = kind or payload.get("kind", "fact")
    if selected_kind not in KINDS:
        raise BrainError("INVALID_KIND", "kind is invalid")
    selected_subject = subject or payload.get("subject")
    if not isinstance(selected_subject, str) or not selected_subject.strip():
        raise BrainError("INVALID_SUBJECT", "subject must be a non-empty string")
    confidence = payload.get("confidence", "confirmed")
    sensitivity = payload.get("sensitivity", "private")
    importance = payload.get("importance", "normal")
    tags = payload.get("tags", [])
    if confidence not in CONFIDENCES:
        raise BrainError("INVALID_CONFIDENCE", "confidence is invalid")
    if sensitivity not in SENSITIVITIES:
        raise BrainError("INVALID_SENSITIVITY", "sensitivity is invalid")
    if importance not in IMPORTANCES:
        raise BrainError("INVALID_IMPORTANCE", "importance is invalid")
    if not isinstance(tags, list) or not all(isinstance(tag, str) and tag.strip() for tag in tags):
        raise BrainError("INVALID_TAGS", "tags must be non-empty strings")
    return {
        "schema": MEMORY_SCHEMA,
        "id": memory_id,
        "kind": selected_kind,
        "subject": selected_subject.strip(),
        "created_at": utc_now(),
        "created_by": identity["id"],
        "confidence": confidence,
        "sensitivity": sensitivity,
        "importance": importance,
        "tags": sorted(set(tag.strip() for tag in tags)),
        "supersedes": supersedes or [],
        "source": source or source_from_input(payload.get("source"), "user-statement"),
    }


def memory_path(root: Path, meta: dict[str, Any]) -> Path:
    timestamp = datetime.fromisoformat(meta["created_at"].replace("Z", "+00:00"))
    agent_short = str(meta["created_by"]).split("-")[0]
    filename = f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}-{agent_short}-{meta['id']}.md"
    return root / "brain" / "memories" / timestamp.strftime("%Y") / timestamp.strftime("%m") / filename


def body_for(meta: dict[str, Any], summary: str) -> str:
    title = str(meta["subject"]).replace("_", " ").replace(".", " / ")
    return f"# {meta['kind'].replace('-', ' ').title()}: {title}\n\n{summary.strip()}"


def exact_duplicate(records: list[Record], subject: str, summary: str) -> Record | None:
    target_subject = normalize(subject)
    target_summary = normalize(summary)
    for record in records:
        if normalize(str(record.meta.get("subject", ""))) == target_subject and normalize(summary_text(record)) == target_summary:
            return record
    return None


def commit_paths(root: Path, paths: list[Path], message: str) -> dict[str, Any]:
    for path in paths:
        run(["git", "add", "--", relative(root, path)], root, check=True)
    committed = run(["git", "commit", "-m", message], root)
    if committed.returncode != 0:
        raise BrainError("COMMIT_FAILED", "Unable to commit memory records", {"stderr": safe_git_error(committed.stderr)})
    if not has_remote(root):
        return {"pushed": False, "pending_sync": True, "reason": "missing_origin"}
    pushed, reason = push_with_retry(root)
    return {"pushed": pushed, "pending_sync": not pushed, "reason": reason}


def create_memory_file(
    root: Path,
    identity: dict[str, Any],
    payload: dict[str, Any],
    *,
    kind: str | None = None,
    subject: str | None = None,
    supersedes: list[str] | None = None,
    source: dict[str, Any] | None = None,
    importing: bool = False,
) -> tuple[Record | None, Record | None, list[str]]:
    validate_candidate(payload, importing=importing)
    records = load_memories(root)
    active, conflicts = current_memories(records)
    selected_subject = subject or payload.get("subject")
    duplicate = exact_duplicate(active, str(selected_subject), str(payload["summary"]))
    if duplicate and not supersedes:
        return None, duplicate, conflicts.get(normalize(str(selected_subject)), [])
    memory_id = str(uuid.uuid4())
    meta = memory_meta(
        payload,
        identity,
        memory_id=memory_id,
        kind=kind,
        subject=subject,
        supersedes=supersedes,
        source=source,
    )
    path = memory_path(root, meta)
    write_record(path, meta, body_for(meta, str(payload["summary"])))
    record = parse_record(path)
    errors = validate_memory(record)
    if errors:
        path.unlink(missing_ok=True)
        raise BrainError("INVALID_MEMORY", "Generated memory failed validation", {"errors": errors})
    subject_key = normalize(str(meta["subject"]))
    subject_conflicts = conflicts.get(subject_key, [])
    if not supersedes:
        existing = [
            str(item.meta["id"])
            for item in active
            if normalize(str(item.meta.get("subject", ""))) == subject_key
            and normalize(summary_text(item)) != normalize(str(payload["summary"]))
        ]
        if existing:
            subject_conflicts = sorted(set([*existing, *subject_conflicts, memory_id]))
    return record, None, subject_conflicts


def command_validate(root: Path) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    memories: list[Record] = []
    agents: list[Record] = []
    imports: list[Record] = []
    required_paths = (
        root / "megabrain.json",
        root / "brain" / "memories",
        root / "brain" / "agents",
        root / "brain" / "imports",
    )
    for path in required_paths:
        if not path.exists():
            errors.append({"path": relative(root, path), "message": "required repository path is missing"})
    if (root / "megabrain.json").exists():
        try:
            manifest = brain_manifest(root)
            if manifest["protocol_version"] > SUPPORTED_PROTOCOL:
                errors.append({"path": "megabrain.json", "message": "brain protocol requires a newer runtime"})
        except BrainError as error:
            errors.append({"path": "megabrain.json", "message": error.message})
    for path, validator, destination in (
        *((path, validate_memory, memories) for path in memory_files(root)),
        *((path, validate_agent, agents) for path in agent_files(root)),
        *((path, validate_import, imports) for path in import_files(root)),
    ):
        try:
            record = parse_record(path)
            destination.append(record)
            for message in validator(record):
                errors.append({"path": relative(root, path), "message": message})
        except BrainError as error:
            errors.append({"path": relative(root, path), "message": error.message})
    memory_ids = [str(record.meta.get("id")) for record in memories]
    agent_ids = [str(record.meta.get("id")) for record in agents]
    import_ids = [str(record.meta.get("id")) for record in imports]
    for label, ids, path in (
        ("memory", memory_ids, "brain/memories"),
        ("agent", agent_ids, "brain/agents"),
        ("import", import_ids, "brain/imports"),
    ):
        for record_id, count in Counter(ids).items():
            if count > 1:
                errors.append({"path": path, "message": f"duplicate {label} id: {record_id}"})
    known_ids = set(memory_ids)
    known_agents = set(agent_ids)
    known_imports = set(import_ids)
    for record in memories:
        if str(record.meta.get("created_by")) not in known_agents:
            errors.append({"path": relative(root, record.path), "message": "created_by agent is not registered"})
        supersedes = record.meta.get("supersedes", [])
        for target in supersedes if isinstance(supersedes, list) else []:
            if target not in known_ids:
                errors.append({"path": relative(root, record.path), "message": f"unknown supersedes id: {target}"})
        source = record.meta.get("source", {})
        import_batch = source.get("import_batch") if isinstance(source, dict) else None
        if import_batch and import_batch not in known_imports:
            errors.append({"path": relative(root, record.path), "message": f"unknown import batch: {import_batch}"})
        if not record.path.name.endswith(f"-{record.meta.get('id')}.md"):
            errors.append({"path": relative(root, record.path), "message": "filename does not contain its memory id"})
        try:
            year, month = record.path.relative_to(root / "brain" / "memories").parts[:2]
            created_at = datetime.fromisoformat(str(record.meta.get("created_at", "")).replace("Z", "+00:00"))
            if (year, month) != (created_at.strftime("%Y"), created_at.strftime("%m")):
                errors.append({"path": relative(root, record.path), "message": "path does not match created_at year/month"})
        except (ValueError, IndexError, TypeError):
            pass
    for record in agents:
        if record.path.stem != str(record.meta.get("id")):
            errors.append({"path": relative(root, record.path), "message": "filename does not match its agent id"})
    for record in imports:
        if str(record.meta.get("created_by")) not in known_agents:
            errors.append({"path": relative(root, record.path), "message": "created_by agent is not registered"})
        if record.path.stem != str(record.meta.get("id")):
            errors.append({"path": relative(root, record.path), "message": "filename does not match its import id"})
    fingerprints = [
        (
            str(record.meta.get("source", {}).get("type")) if isinstance(record.meta.get("source"), dict) else "",
            str(record.meta.get("source", {}).get("locator")) if isinstance(record.meta.get("source"), dict) else "",
            str(record.meta.get("source", {}).get("hash")) if isinstance(record.meta.get("source"), dict) else "",
        )
        for record in imports
    ]
    for fingerprint, count in Counter(fingerprints).items():
        if count > 1:
            warnings.append({"path": "brain/imports", "message": "duplicate source fingerprint", "fingerprint": list(fingerprint)})
    active, conflicts = current_memories(memories)
    for subject, conflict_ids in sorted(conflicts.items()):
        warnings.append({"subject": subject, "message": "multiple current values", "memory_ids": conflict_ids})
    return {
        "ok": not errors,
        "counts": {"memories": len(memories), "current": len(active), "agents": len(agents), "imports": len(imports)},
        "errors": errors,
        "warnings": warnings,
    }


def compiled_task(payload: dict[str, Any]) -> str:
    task = payload.get("task")
    if isinstance(task, str):
        values = [task]
    elif isinstance(task, dict):
        allowed = ("task", "artifact_type", "domain", "intent", "audience", "subject_family")
        unknown = sorted(set(task) - set(allowed))
        if unknown:
            raise BrainError("INVALID_TASK", "structured task contains unsupported fields")
        values = []
        for field in allowed:
            value = task.get(field)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise BrainError("INVALID_TASK", "structured task fields must be non-empty strings")
            if isinstance(value, str):
                values.append(value)
    else:
        values = []
    if not values or not any(value.strip() for value in values):
        raise BrainError("INVALID_TASK", "task must be a non-empty string or structured task")
    if detect_secret(values):
        raise BrainError("SECRET_VALUE_REJECTED", "Likely secret material cannot be used as retrieval evidence")
    return " ".join(value.strip() for value in values)


def retrieval_index_path(root: Path) -> Path:
    return root / ".megabrain" / "retrieval-index.sqlite3"


def build_retrieval_index(root: Path, commit: str, path: Path) -> dict[str, float]:
    started = time.perf_counter()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix=".retrieval-tree-", dir=path.parent) as tree_name:
        snapshot_root = Path(tree_name)
        archived = subprocess.Popen(
            ["git", "archive", "--format=tar", commit, "--", "brain"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert archived.stdout is not None
        try:
            with tarfile.open(fileobj=archived.stdout, mode="r|") as archive:
                for member in archive:
                    member_path = Path(member.name)
                    if member_path.is_absolute() or ".." in member_path.parts or member.issym() or member.islnk():
                        raise BrainError("INDEX_SNAPSHOT_INVALID", "The committed Brain archive contains an unsafe path")
                    archive.extract(member, snapshot_root)
        except BrainError:
            archived.kill()
            archived.wait()
            raise
        except (tarfile.TarError, OSError) as error:
            archived.kill()
            archived.wait()
            raise BrainError("INDEX_SNAPSHOT_FAILED", "The committed Brain snapshot could not be read") from error
        finally:
            archived.stdout.close()
        stderr = archived.stderr.read().decode("utf-8", errors="replace") if archived.stderr is not None else ""
        if archived.stderr is not None:
            archived.stderr.close()
        if archived.wait() != 0:
            raise BrainError("INDEX_SNAPSHOT_FAILED", "The committed Brain snapshot could not be read", {"git": stderr.strip()})
        records = load_memories(snapshot_root)
        loaded_at = time.perf_counter()
        active, conflicts = current_memories(records)
        resolved_at = time.perf_counter()
        descriptor, temporary_name = tempfile.mkstemp(prefix=".retrieval-index-", dir=path.parent)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            connection = sqlite3.connect(temporary)
            connection.executescript(
                """
                PRAGMA journal_mode=OFF;
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE records (
                    id TEXT PRIMARY KEY, path TEXT NOT NULL, meta_json TEXT NOT NULL,
                    summary TEXT NOT NULL, importance TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE postings (token TEXT NOT NULL, record_id TEXT NOT NULL, weight INTEGER NOT NULL,
                    PRIMARY KEY(token, record_id));
                CREATE INDEX postings_record ON postings(record_id);
                CREATE TABLE conflicts (subject TEXT NOT NULL, record_id TEXT NOT NULL,
                    PRIMARY KEY(subject, record_id));
                """
            )
            connection.executemany(
                "INSERT INTO metadata VALUES (?, ?)",
                (("schema", RETRIEVAL_INDEX_SCHEMA), ("commit", commit)),
            )
            for record in active:
                record_id = str(record.meta["id"])
                summary = summary_text(record)
                connection.execute(
                    "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        record_id,
                        relative(snapshot_root, record.path),
                        json.dumps(record.meta, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
                        summary,
                        record.meta.get("importance", "normal"),
                        record.meta.get("created_at", ""),
                    ),
                )
                subject_tokens = tokens(str(record.meta.get("subject", "")))
                tag_tokens = tokens(" ".join(str(tag) for tag in record.meta.get("tags", [])))
                body_tokens = tokens(summary)
                weighted = {
                    token: 6 * (token in subject_tokens) + 4 * (token in tag_tokens) + (token in body_tokens)
                    for token in subject_tokens | tag_tokens | body_tokens
                }
                connection.executemany(
                    "INSERT INTO postings VALUES (?, ?, ?)",
                    ((token, record_id, weight) for token, weight in weighted.items()),
                )
            connection.executemany(
                "INSERT INTO conflicts VALUES (?, ?)",
                ((subject, record_id) for subject, ids in conflicts.items() for record_id in ids),
            )
            connection.commit()
            connection.close()
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    return {
        "local_index_refresh": loaded_at - started,
        "memory_graph_resolution": resolved_at - loaded_at,
    }


def open_retrieval_index(
    root: Path,
    *,
    allow_rebuild: bool = True,
) -> tuple[sqlite3.Connection, str, dict[str, float]]:
    started = time.perf_counter()
    commit = git_commit(root)
    path = retrieval_index_path(root)
    if not commit:
        raise BrainError("INDEX_UNAVAILABLE", "Retrieval indexing requires a Git commit")
    if not path.exists() and not allow_rebuild:
        raise BrainError(
            "DIRTY_WORKTREE_INDEX_UNAVAILABLE",
            "Retrieval will not compile uncommitted Brain content into the persistent index",
        )
    state = "warm"
    timings = {"local_index_refresh": 0.0, "memory_graph_resolution": 0.0}
    try:
        connection = sqlite3.connect(path)
        metadata = dict(connection.execute("SELECT key,value FROM metadata"))
        if metadata != {"schema": RETRIEVAL_INDEX_SCHEMA, "commit": commit}:
            raise sqlite3.DatabaseError("stale index")
    except (OSError, sqlite3.DatabaseError):
        try:
            connection.close()
        except UnboundLocalError:
            pass
        path.unlink(missing_ok=True)
        if not allow_rebuild:
            raise BrainError(
                "DIRTY_WORKTREE_INDEX_UNAVAILABLE",
                "Retrieval will not compile uncommitted Brain content into the persistent index",
            )
        timings = build_retrieval_index(root, commit, path)
        state = "cold"
        connection = sqlite3.connect(path)
    if state == "warm":
        timings["local_index_refresh"] = time.perf_counter() - started
    return connection, state, timings


def row_record(root: Path, row: sqlite3.Row | tuple[Any, ...]) -> Record:
    return Record(path=root / str(row[1]), meta=json.loads(row[2]), body=str(row[3]))


def indexed_memories(
    root: Path,
    task_tokens: set[str],
    *,
    allow_rebuild: bool = True,
) -> tuple[list[tuple[int, Record]], dict[str, list[str]], str, dict[str, float]]:
    connection, state, timings = open_retrieval_index(root, allow_rebuild=allow_rebuild)
    try:
        scores: dict[str, int] = {}
        if task_tokens:
            placeholders = ",".join("?" for _ in task_tokens)
            scores = {
                record_id: score
                for record_id, score in connection.execute(
                    f"SELECT record_id,SUM(weight) FROM postings WHERE token IN ({placeholders}) GROUP BY record_id",
                    sorted(task_tokens),
                )
            }
        always_ids = {
            row[0] for row in connection.execute("SELECT id FROM records WHERE importance='always'")
        }
        candidate_ids = set(scores) | always_ids
        candidates: list[tuple[int, Record]] = []
        if candidate_ids:
            placeholders = ",".join("?" for _ in candidate_ids)
            for row in connection.execute(
                f"SELECT id,path,meta_json,summary FROM records WHERE id IN ({placeholders})",
                sorted(candidate_ids),
            ):
                candidates.append((scores.get(row[0], 0), row_record(root, row)))
        conflicts: dict[str, list[str]] = defaultdict(list)
        for subject, record_id in connection.execute("SELECT subject,record_id FROM conflicts ORDER BY subject,record_id"):
            conflicts[subject].append(record_id)
        return candidates, dict(conflicts), state, timings
    finally:
        connection.close()


def indexed_record(root: Path, memory_id: str) -> Record | None:
    path = retrieval_index_path(root)
    try:
        connection = sqlite3.connect(path)
        row = connection.execute(
            "SELECT id,path,meta_json,summary FROM records WHERE id=?", (memory_id,)
        ).fetchone()
    except sqlite3.DatabaseError:
        return None
    finally:
        try:
            connection.close()
        except UnboundLocalError:
            pass
    return row_record(root, row) if row else None


def command_context(root: Path, payload: dict[str, Any], limit: int) -> dict[str, Any]:
    total_started = time.perf_counter()
    stage_started = total_started
    compatibility = require_compatible_runtime(root, writing=False)
    runtime_elapsed = time.perf_counter() - stage_started
    task = compiled_task(payload)
    fresh = payload.get("fresh", False)
    diagnostic = payload.get("diagnostic", False)
    freshness_seconds = payload.get("freshness_seconds", DEFAULT_FRESHNESS_SECONDS)
    if not isinstance(fresh, bool) or not isinstance(diagnostic, bool):
        raise BrainError("INVALID_TASK", "fresh and diagnostic must be booleans")
    if not isinstance(freshness_seconds, int) or not 0 <= freshness_seconds <= 300:
        raise BrainError("INVALID_TASK", "freshness_seconds must be between 0 and 300")
    stage_started = time.perf_counter()
    sync = sync_repo(
        root,
        allow_push=runtime_can_write(compatibility),
        fresh=fresh,
        freshness_seconds=freshness_seconds,
    )
    sync_elapsed = time.perf_counter() - stage_started
    if sync.get("reason") == "validation_failed":
        raise BrainError("BRAIN_INVALID", "The local brain failed validation", sync)
    task_tokens = tokens(task)
    candidates, conflicts, index_state, index_timings = indexed_memories(
        root,
        task_tokens,
        allow_rebuild=sync.get("reason") != "dirty_worktree",
    )
    stage_started = time.perf_counter()
    ranked = [
        (score, record)
        for score, record in candidates
        if score > 0 and record.meta.get("importance") != "always"
    ]
    ranked.sort(
        key=lambda item: (
            item[0],
            item[1].meta.get("importance") == "core",
            item[1].meta.get("created_at", ""),
            item[1].meta.get("id", ""),
        ),
        reverse=True,
    )
    always = [
        (score, record)
        for score, record in candidates
        if record.meta.get("importance") == "always"
    ]
    always.sort(key=lambda item: (item[0], item[1].meta.get("created_at", "")), reverse=True)
    selected = [*always[:ALWAYS_MEMORY_LIMIT], *ranked]
    selected = selected[:limit]
    selected_ids = {str(record.meta["id"]) for _, record in selected}
    conflict_expansion = 0
    active_by_id = {str(record.meta["id"]): record for _, record in candidates}
    for ids in conflicts.values():
        if selected_ids.intersection(ids):
            for memory_id in ids:
                if memory_id not in selected_ids and conflict_expansion < CONFLICT_EXPANSION_LIMIT:
                    record = active_by_id.get(memory_id) or indexed_record(root, memory_id)
                    if record:
                        selected.append((score_memory(record, task_tokens), record))
                        selected_ids.add(memory_id)
                        conflict_expansion += 1
    selected_conflicts = [
        {"subject": subject, "memory_ids": ids}
        for subject, ids in sorted(conflicts.items())
        if selected_ids.intersection(ids)
    ]
    ranking_elapsed = time.perf_counter() - stage_started
    conflicting_ids = {item for conflict in conflicts.values() for item in conflict}
    result: dict[str, Any] = {
        "ok": True,
        "sync": sync,
        "stale": not sync.get("synced", False),
        "limit": limit,
        "conflict_expansion": conflict_expansion,
        "memories": [
            {
                "id": record.meta["id"],
                "kind": record.meta["kind"],
                "subject": record.meta["subject"],
                "summary": summary_text(record),
                "confidence": record.meta["confidence"],
                "sensitivity": record.meta["sensitivity"],
                "importance": record.meta["importance"],
                "tags": record.meta["tags"],
                "score": score,
                "conflict": str(record.meta["id"]) in conflicting_ids,
                **(
                    {
                        "provenance": {
                            "created_at": record.meta["created_at"],
                            "created_by": record.meta["created_by"],
                            "source": record.meta["source"],
                        }
                    }
                    if str(record.meta["id"]) in conflicting_ids
                    else {}
                ),
            }
            for score, record in selected
        ],
        "conflicts": selected_conflicts,
    }
    serialization_started = time.perf_counter()
    json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    serialization_elapsed = time.perf_counter() - serialization_started
    if diagnostic:
        result["diagnostics"] = {
            "index": index_state,
            "freshness_window_seconds": freshness_seconds,
            "timings_ms": {
                "runtime_check": round(runtime_elapsed * 1000, 3),
                "remote_synchronization": round(sync_elapsed * 1000, 3),
                "local_index_refresh": round(index_timings["local_index_refresh"] * 1000, 3),
                "memory_graph_resolution": round(index_timings["memory_graph_resolution"] * 1000, 3),
                "ranking_and_collection_expansion": round(ranking_elapsed * 1000, 3),
                "serialization": round(serialization_elapsed * 1000, 3),
                "total": round((time.perf_counter() - total_started) * 1000, 3),
            },
        }
    return result


def command_remember(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    require_compatible_runtime(root, writing=True)
    identity = load_identity(root)
    sync = sync_repo(root)
    require_clean_or_offline(sync)
    record, duplicate, conflict_ids = create_memory_file(root, identity, payload)
    if duplicate:
        return {"ok": True, "created": False, "duplicate_of": duplicate.meta["id"], "sync": sync}
    assert record is not None
    result = commit_paths(root, [record.path], f"memory({identity['harness']}): {record.meta['kind']} {record.meta['subject']}")
    return {
        "ok": True,
        "created": True,
        "memory_id": record.meta["id"],
        "conflict": bool(conflict_ids),
        "conflict_memory_ids": conflict_ids,
        "notice": "MegaBrain: saved 1 durable memory.",
        **result,
    }


def find_memory(root: Path, memory_id: str) -> tuple[Record, bool]:
    records = load_memories(root)
    active, _ = current_memories(records)
    by_id = {str(record.meta.get("id")): record for record in records}
    record = by_id.get(memory_id)
    if not record:
        raise BrainError("MEMORY_NOT_FOUND", "Memory ID was not found")
    return record, any(item.meta.get("id") == memory_id for item in active)


def command_correct(root: Path, memory_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    require_compatible_runtime(root, writing=True)
    identity = load_identity(root)
    sync = sync_repo(root)
    require_clean_or_offline(sync)
    previous, is_current = find_memory(root, memory_id)
    if not is_current:
        raise BrainError("MEMORY_NOT_CURRENT", "Only a current memory can be corrected")
    payload = dict(payload)
    payload.setdefault("confidence", "confirmed")
    payload.setdefault("sensitivity", previous.meta["sensitivity"])
    payload.setdefault("importance", previous.meta["importance"])
    payload.setdefault("tags", previous.meta["tags"])
    record, duplicate, _ = create_memory_file(
        root,
        identity,
        payload,
        kind="correction",
        subject=str(previous.meta["subject"]),
        supersedes=[memory_id],
    )
    if duplicate:
        return {"ok": True, "created": False, "duplicate_of": duplicate.meta["id"], "sync": sync}
    assert record is not None
    result = commit_paths(root, [record.path], f"memory({identity['harness']}): correct {record.meta['subject']}")
    return {
        "ok": True,
        "created": True,
        "memory_id": record.meta["id"],
        "supersedes": memory_id,
        "notice": "MegaBrain: saved 1 durable correction.",
        **result,
    }


def command_forget(root: Path, memory_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    require_compatible_runtime(root, writing=True)
    identity = load_identity(root)
    sync = sync_repo(root)
    require_clean_or_offline(sync)
    previous, is_current = find_memory(root, memory_id)
    if not is_current:
        raise BrainError("MEMORY_NOT_CURRENT", "Only a current memory can be forgotten")
    reason = payload.get("reason", "The owner requested that this memory no longer be used.")
    if not isinstance(reason, str) or not reason.strip():
        raise BrainError("INVALID_REASON", "reason must be a non-empty string")
    tombstone_payload = {
        "summary": reason,
        "confidence": "confirmed",
        "sensitivity": previous.meta["sensitivity"],
        "importance": "normal",
        "tags": previous.meta["tags"],
        "source": payload.get("source", {"type": "user-statement"}),
    }
    record, _, _ = create_memory_file(
        root,
        identity,
        tombstone_payload,
        kind="tombstone",
        subject=str(previous.meta["subject"]),
        supersedes=[memory_id],
    )
    assert record is not None
    result = commit_paths(root, [record.path], f"memory({identity['harness']}): forget {record.meta['subject']}")
    return {
        "ok": True,
        "created": True,
        "tombstone_id": record.meta["id"],
        "supersedes": memory_id,
        "notice": "MegaBrain: forgot 1 current memory (Git history is retained).",
        **result,
    }


def prior_import(root: Path, source: dict[str, str]) -> Record | None:
    for record in load_records(import_files(root)):
        previous = record.meta.get("source", {})
        if previous.get("type") == source["type"] and previous.get("locator") == source["locator"] and previous.get("hash") == source["hash"]:
            return record
    return None


def import_coverage(value: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if value is None:
        return [], {
            "writable": 0,
            "reference_only": 0,
            "excluded": 0,
            "scanned": 0,
            "candidates_extracted": 0,
            "intentionally_skipped": 0,
            "canonical_not_scanned": [],
        }
    if not isinstance(value, list):
        raise BrainError("INVALID_SOURCE_COVERAGE", "coverage must be an array")
    entries: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise BrainError("INVALID_SOURCE_COVERAGE", "coverage entries must be objects")
        entry = {
            "locator": raw.get("locator"),
            "access": raw.get("access"),
            "canonical": raw.get("canonical", False),
            "status": raw.get("status"),
        }
        if (
            not isinstance(entry["locator"], str)
            or not entry["locator"].strip()
            or entry["access"] not in {"writable", "reference-only", "excluded"}
            or not isinstance(entry["canonical"], bool)
            or entry["status"] not in {"discovered", "scanned", "candidate-extracted", "intentionally-skipped"}
        ):
            raise BrainError("INVALID_SOURCE_COVERAGE", "coverage entries are invalid")
        if detect_secret(entry):
            raise BrainError("SECRET_VALUE_REJECTED", "Likely secret material cannot be stored in source coverage")
        entries.append(entry)
    summary = {
        "writable": sum(entry["access"] == "writable" for entry in entries),
        "reference_only": sum(entry["access"] == "reference-only" for entry in entries),
        "excluded": sum(entry["access"] == "excluded" for entry in entries),
        "scanned": sum(entry["status"] in {"scanned", "candidate-extracted"} for entry in entries),
        "candidates_extracted": sum(entry["status"] == "candidate-extracted" for entry in entries),
        "intentionally_skipped": sum(entry["status"] == "intentionally-skipped" for entry in entries),
        "canonical_not_scanned": [
            entry["locator"]
            for entry in entries
            if entry["canonical"] and entry["status"] == "discovered" and entry["access"] != "excluded"
        ],
    }
    return entries, summary


def command_ingest(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    require_compatible_runtime(root, writing=True)
    identity = load_identity(root)
    sync = sync_repo(root)
    require_clean_or_offline(sync)
    source_input = payload.get("source")
    if not isinstance(source_input, dict):
        raise BrainError("INVALID_IMPORT_SOURCE", "source must be an object")
    source = {key: source_input.get(key) for key in ("type", "locator", "hash")}
    if not all(isinstance(value, str) and value.strip() for value in source.values()):
        raise BrainError("INVALID_IMPORT_SOURCE", "source type, locator, and hash are required")
    source = {key: str(value).strip() for key, value in source.items()}
    if not SHA256_PATTERN.fullmatch(source["hash"]):
        raise BrainError("INVALID_IMPORT_SOURCE", "source.hash must be a SHA-256 fingerprint")
    coverage, coverage_summary = import_coverage(payload.get("coverage"))
    previous = prior_import(root, source)
    if previous:
        return {
            "ok": True,
            "status": "unchanged",
            "import_id": previous.meta["id"],
            "counts": previous.meta["counts"],
            "coverage": coverage_summary,
            "sync": sync,
        }
    candidates = payload.get("memories")
    if not isinstance(candidates, list):
        raise BrainError("INVALID_IMPORT", "memories must be an array")
    batch_id = str(uuid.uuid4())
    created: list[Record] = []
    duplicate_ids: list[str] = []
    conflicts: list[dict[str, Any]] = []
    rejected: Counter[str] = Counter()
    shared_source = {"type": "import", "locator": source["locator"], "hash": source["hash"], "import_batch": batch_id}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            rejected["invalid_candidate"] += 1
            continue
        candidate = dict(candidate)
        candidate.setdefault("confidence", "unconfirmed")
        try:
            record, duplicate, conflict_ids = create_memory_file(
                root,
                identity,
                candidate,
                source=shared_source,
                importing=True,
            )
        except BrainError as error:
            rejected[error.code.lower()] += 1
            continue
        if duplicate:
            duplicate_ids.append(str(duplicate.meta["id"]))
            continue
        assert record is not None
        created.append(record)
        if conflict_ids:
            conflicts.append({"subject": record.meta["subject"], "memory_ids": conflict_ids})
    counts = {
        "scanned": len(candidates),
        "created": len(created),
        "duplicates": len(duplicate_ids),
        "conflicts": len(conflicts),
        "rejected": sum(rejected.values()),
    }
    import_meta = {
        "schema": IMPORT_SCHEMA,
        "id": batch_id,
        "created_at": utc_now(),
        "created_by": identity["id"],
        "source": source,
        "counts": counts,
        "created_memory_ids": [record.meta["id"] for record in created],
        "duplicate_memory_ids": duplicate_ids,
        "conflicts": conflicts,
        "rejected_by_code": dict(sorted(rejected.items())),
        "coverage": coverage,
    }
    manifest = root / "brain" / "imports" / f"{batch_id}.md"
    write_record(
        manifest,
        import_meta,
        "# Import Batch\n\nThis manifest records an agent-mediated durable-summary import. Raw source content is not stored.",
    )
    errors = validate_import(parse_record(manifest))
    if errors:
        manifest.unlink(missing_ok=True)
        for record in created:
            record.path.unlink(missing_ok=True)
        raise BrainError("INVALID_IMPORT_MANIFEST", "Import manifest failed validation", {"errors": errors})
    validation = command_validate(root)
    if not validation["ok"]:
        manifest.unlink(missing_ok=True)
        for record in created:
            record.path.unlink(missing_ok=True)
        raise BrainError("IMPORT_VALIDATION_FAILED", "Import would make the brain invalid", {"errors": validation["errors"]})
    result = commit_paths(
        root,
        [*(record.path for record in created), manifest],
        f"memory({identity['harness']}): ingest {len(created)} durable summaries",
    )
    return {
        "ok": True,
        "status": "imported",
        "import_id": batch_id,
        "counts": counts,
        "created_memory_ids": import_meta["created_memory_ids"],
        "duplicate_memory_ids": duplicate_ids,
        "conflicts": conflicts,
        "rejected_by_code": import_meta["rejected_by_code"],
        "coverage": coverage_summary,
        "notice": f"MegaBrain: imported {len(created)} durable memories; {counts['duplicates']} duplicates, {counts['conflicts']} conflicts, {counts['rejected']} rejected.",
        **result,
    }


def command_agents(root: Path) -> dict[str, Any]:
    sync = sync_repo(root)
    if sync.get("reason") == "validation_failed":
        raise BrainError("BRAIN_INVALID", "The local brain failed validation", sync)
    memories = load_memories(root)
    contributions = Counter(str(record.meta.get("created_by")) for record in memories)
    agents = []
    for record in load_records(agent_files(root)):
        agents.append(
            {
                "id": record.meta.get("id"),
                "display_name": record.meta.get("display_name"),
                "harness": record.meta.get("harness"),
                "created_at": record.meta.get("created_at"),
                "contributions": contributions[str(record.meta.get("id"))],
            }
        )
    return {"ok": True, "sync": sync, "agents": agents}


def browser_payload(root: Path, sync: dict[str, Any]) -> dict[str, Any]:
    records = load_memories(root)
    active, conflicts = current_memories(records)
    active_ids = {str(record.meta.get("id")) for record in active}
    conflict_ids = {memory_id for ids in conflicts.values() for memory_id in ids}
    superseded_by: dict[str, list[str]] = defaultdict(list)
    for record in records:
        supersedes = record.meta.get("supersedes", [])
        for memory_id in supersedes if isinstance(supersedes, list) else []:
            superseded_by[str(memory_id)].append(str(record.meta.get("id")))
    memories = []
    contributions = Counter(str(record.meta.get("created_by")) for record in records)
    for record in sorted(records, key=lambda item: str(item.meta.get("created_at", "")), reverse=True):
        memory_id = str(record.meta.get("id"))
        if record.meta.get("kind") == "tombstone":
            status = "tombstone"
        elif memory_id in active_ids:
            status = "current"
        else:
            status = "historical"
        memories.append(
            {
                "id": memory_id,
                "kind": record.meta.get("kind"),
                "subject": record.meta.get("subject"),
                "summary": summary_text(record),
                "created_at": record.meta.get("created_at"),
                "created_by": record.meta.get("created_by"),
                "confidence": record.meta.get("confidence"),
                "sensitivity": record.meta.get("sensitivity"),
                "importance": record.meta.get("importance"),
                "tags": record.meta.get("tags", []),
                "source": record.meta.get("source", {}),
                "supersedes": record.meta.get("supersedes", []),
                "superseded_by": superseded_by.get(memory_id, []),
                "status": status,
                "conflict": memory_id in conflict_ids,
                "path": relative(root, record.path),
            }
        )
    agents = [
        {
            "id": str(record.meta.get("id")),
            "display_name": record.meta.get("display_name"),
            "harness": record.meta.get("harness"),
            "created_at": record.meta.get("created_at"),
            "contributions": contributions[str(record.meta.get("id"))],
        }
        for record in load_records(agent_files(root))
    ]
    imports = [
        {
            "id": str(record.meta.get("id")),
            "created_at": record.meta.get("created_at"),
            "created_by": record.meta.get("created_by"),
            "source": record.meta.get("source", {}),
            "counts": record.meta.get("counts", {}),
            "created_memory_ids": record.meta.get("created_memory_ids", []),
            "duplicate_memory_ids": record.meta.get("duplicate_memory_ids", []),
            "conflicts": record.meta.get("conflicts", []),
            "rejected_by_code": record.meta.get("rejected_by_code", {}),
            "path": relative(root, record.path),
        }
        for record in sorted(
            load_records(import_files(root)),
            key=lambda item: str(item.meta.get("created_at", "")),
            reverse=True,
        )
    ]
    return {
        "generated_at": utc_now(),
        "sync": sync,
        "stats": {
            "current": len(active),
            "history": len(records) - len(active),
            "conflicts": len(conflicts),
            "agents": len(agents),
            "imports": len(imports),
        },
        "memories": memories,
        "conflicts": [
            {"subject": subject, "memory_ids": memory_ids}
            for subject, memory_ids in sorted(conflicts.items())
        ],
        "agents": agents,
        "imports": imports,
    }


def command_browse(root: Path, no_open: bool) -> dict[str, Any]:
    compatibility = require_compatible_runtime(root, writing=False)
    sync = sync_repo(root, allow_push=runtime_can_write(compatibility))
    validation = command_validate(root)
    if not validation["ok"]:
        raise BrainError(
            "BRAIN_INVALID",
            "The local brain must pass validation before it can be browsed",
            {"error_count": len(validation["errors"])},
        )
    template = Path(__file__).resolve().parents[1] / "assets" / "browser.html"
    if not template.exists():
        raise BrainError("BROWSER_TEMPLATE_MISSING", "The local browser template is missing")
    serialized = json.dumps(browser_payload(root, sync), ensure_ascii=True, sort_keys=True)
    serialized = (
        serialized.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    html = template.read_text(encoding="utf-8").replace("__MEGABRAIN_DATA__", serialized)
    output = root / ".megabrain" / "browser" / "index.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    opened = False if no_open else webbrowser.open(output.resolve().as_uri())
    return {
        "ok": True,
        "generated": True,
        "opened": opened,
        "path": str(output),
        "host": os.uname().nodename,
        "sync": sync,
    }


def github_repo_from_remote(remote: str) -> str | None:
    match = re.search(r"github\.com[/:]([^/]+/[^/.]+)(?:\.git)?$", remote)
    return match.group(1) if match else None


def command_doctor(root: Path) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "python": {"ok": sys.version_info >= (3, 10), "version": ".".join(map(str, sys.version_info[:3]))},
        "git": {"ok": shutil.which("git") is not None},
        "repository": {"ok": is_git_repo(root)},
        "identity": {"ok": local_config_path(root).exists()},
        "worktree": {"ok": not changed_files(root), "files": changed_files(root)},
    }
    remote_result = run(["git", "remote", "get-url", "origin"], root) if is_git_repo(root) else None
    remote = remote_result.stdout.strip() if remote_result and remote_result.returncode == 0 else ""
    checks["origin"] = {"ok": bool(remote), "configured": bool(remote)}
    remote_access = run(["git", "ls-remote", "--exit-code", "origin", "HEAD"], root) if remote else None
    checks["remote_access"] = {"ok": bool(remote_access and remote_access.returncode == 0)}
    repository = github_repo_from_remote(remote)
    privacy: dict[str, Any] = {"ok": False, "status": "unverified"}
    if repository and shutil.which("gh"):
        viewed = run(["gh", "repo", "view", repository, "--json", "visibility", "--jq", ".visibility"], root)
        if viewed.returncode == 0:
            visibility = viewed.stdout.strip().upper()
            privacy = {"ok": visibility == "PRIVATE", "status": visibility.lower()}
    elif remote and not repository:
        privacy = {"ok": False, "status": "non_github_remote"}
    checks["privacy"] = privacy
    try:
        compatibility = require_compatible_runtime(root, writing=False)
        checks["compatibility"] = {
            "ok": runtime_can_write(compatibility),
            "runtime_version": compatibility["runtime"]["version"],
            "minimum_runtime": compatibility["brain"]["minimum_runtime"],
            "protocol_version": compatibility["brain"]["protocol_version"],
        }
    except BrainError as error:
        checks["compatibility"] = {"ok": False, "reason": error.code.lower()}
    validation = command_validate(root)
    checks["validation"] = {"ok": validation["ok"], "errors": len(validation["errors"]), "warnings": len(validation["warnings"])}
    return {"ok": all(check["ok"] for check in checks.values()), "checks": checks}


def vault_brain_id(root: Path, *, create: bool = False) -> str | None:
    manifest = brain_manifest(root)
    value = manifest.get("brain_id")
    if valid_uuid(value):
        return str(value)
    if not create:
        return None
    sync = sync_repo(root, fresh=True)
    require_clean_or_offline(sync)
    value = str(uuid.uuid4())
    manifest["brain_id"] = value
    path = root / "megabrain.json"
    path.write_text(json.dumps(manifest, ensure_ascii=True, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    commit_paths(root, [path], "chore: assign stable brain identifier")
    return value


def write_recovery_file(path: Path, recovery_key: str) -> None:
    if not path.parent.is_dir():
        raise vault_module.VaultError("RECOVERY_FILE_FAILED", "The recovery file directory does not exist.")
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise vault_module.VaultError("RECOVERY_FILE_EXISTS", "The selected recovery file already exists.") from error
    except OSError as error:
        raise vault_module.VaultError("RECOVERY_FILE_FAILED", "The recovery file could not be created.") from error
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(recovery_key + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, 0o600)
    except OSError as error:
        path.unlink(missing_ok=True)
        raise vault_module.VaultError("RECOVERY_FILE_FAILED", "The recovery file could not be created.") from error


def start_vault_broker(root: Path, store: vault_module.VaultStore, master_key: bytes, timeout: int) -> dict[str, Any]:
    socket_path = store.paths.runtime / "broker.sock"
    if socket_path.exists():
        try:
            vault_module.broker_socket_request(socket_path, {"method": "owner.status"})
            return {"ok": True, "unlocked": True, "already_unlocked": True}
        except vault_module.VaultError:
            pass
    environment = dict(os.environ)
    environment["MEGABRAIN_ROOT"] = str(root)
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "vault", "_serve", "--stdin"],
        cwd=root,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )
    assert process.stdin is not None
    process.stdin.write(json.dumps({"master_key": vault_module.b64(master_key), "idle_timeout": timeout}))
    process.stdin.close()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if socket_path.exists():
            try:
                vault_module.broker_socket_request(socket_path, {"method": "owner.status"})
                return {"ok": True, "unlocked": True, "idle_timeout": timeout}
            except vault_module.VaultError:
                pass
        if process.poll() is not None:
            break
        time.sleep(0.05)
    raise vault_module.VaultError("BROKER_START_FAILED", "The local Vault broker did not start.")


def command_vault(root: Path, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    require_compatible_runtime(root, writing=action not in {"status", "doctor", "metadata", "reveal", "audit"})
    vault_module.configure_dependency(Path.home())
    if action == "setup":
        if not payload.get("confirm_recovery_saved", False):
            vault_module.ensure_dependency(Path.home())
        brain_id = vault_brain_id(root, create=not payload.get("confirm_recovery_saved", False))
        if brain_id is None:
            raise vault_module.VaultError("BRAIN_ID_REQUIRED", "Assign a stable brain identifier before Vault setup.")
        store = vault_module.VaultStore(vault_module.paths_for(Path.home(), brain_id))
        if payload.get("confirm_recovery_saved") is True:
            store.confirm_setup()
            return {"ok": True, "ready": True, "recovery_key_displayed": False}
        passphrase = payload.get("passphrase")
        if not isinstance(passphrase, str):
            raise vault_module.VaultError("PASSPHRASE_REQUIRED", "Provide the Vault passphrase through standard input.")
        recovery_path = payload.get("recovery_path")
        selected_recovery: Path | None = None
        if recovery_path is not None:
            if not isinstance(recovery_path, str) or not recovery_path:
                raise vault_module.VaultError("INVALID_RECOVERY_PATH", "Recovery path must be an explicit path string.")
            selected_recovery = Path(recovery_path).expanduser().resolve()
            if selected_recovery.exists():
                raise vault_module.VaultError("RECOVERY_FILE_EXISTS", "The selected recovery file already exists.")
        store, recovery_key = vault_module.VaultStore.setup(store.paths, brain_id, passphrase)
        if selected_recovery is not None:
            try:
                write_recovery_file(selected_recovery, recovery_key)
            except Exception:
                shutil.rmtree(store.paths.root, ignore_errors=True)
                raise
            return {
                "ok": True,
                "created": True,
                "ready": False,
                "confirmation_required": True,
                "recovery_file": str(selected_recovery),
            }
        return {
            "ok": True,
            "created": True,
            "ready": False,
            "confirmation_required": True,
            "recovery_key": recovery_key,
        }

    brain_id = vault_brain_id(root)
    if brain_id is None:
        if action == "status":
            return {"ok": True, "exists": False, "locked": True, "brain_id_assigned": False}
        raise vault_module.VaultError("BRAIN_ID_REQUIRED", "Run vault setup to assign a stable brain identifier.")
    store = vault_module.VaultStore(vault_module.paths_for(Path.home(), brain_id))
    if action == "status":
        return store.status()
    if action == "doctor":
        return vault_module.doctor(store)
    if action == "_serve":
        encoded = payload.get("master_key")
        if not isinstance(encoded, str):
            raise vault_module.VaultError("UNLOCK_MATERIAL_REQUIRED", "Broker unlock material is missing.")
        vault_module.serve_broker(store, vault_module.unb64(encoded), int(payload.get("idle_timeout", 300)))
        return {"ok": True, "locked": True}
    if action == "lock":
        return vault_module.lock_broker(store)
    if action == "metadata":
        identity = load_identity(root)
        request = vault_module.signed_request(
            root,
            {
                "method": action,
                "resource": payload.get("resource"),
                "fields": payload.get("fields", []),
                "purpose": payload.get("purpose"),
                "context": payload.get("context", {"kind": "unknown"}),
            },
        )
        if request["agent_id"] != identity["id"]:
            raise vault_module.VaultError("AGENT_KEY_MISMATCH", "The local Vault key belongs to another agent.")
        return vault_module.broker_socket_request(store.paths.runtime / "broker.sock", request)
    if action == "restore":
        source = payload.get("source")
        if not isinstance(source, str):
            raise vault_module.VaultError("BACKUP_REQUIRED", "Restore requires an explicit backup path.")
        return vault_module.restore_backup(
            Path(source).expanduser().resolve(),
            store.paths,
            passphrase=payload.get("passphrase") if isinstance(payload.get("passphrase"), str) else None,
            recovery_key=payload.get("recovery_key") if isinstance(payload.get("recovery_key"), str) else None,
        )

    passphrase = payload.get("passphrase")
    recovery_key = payload.get("recovery_key")
    master_key = store.unlock(
        passphrase=passphrase if isinstance(passphrase, str) else None,
        recovery_key=recovery_key if isinstance(recovery_key, str) else None,
    )
    if action == "unlock":
        timeout = payload.get("idle_timeout", 300)
        if not isinstance(timeout, int):
            raise vault_module.VaultError("INVALID_TIMEOUT", "Vault idle timeout must be an integer.")
        return start_vault_broker(root, store, master_key, timeout)
    if action == "put":
        item = payload.get("item")
        if not isinstance(item, dict):
            raise vault_module.VaultError("INVALID_ITEM", "Vault put requires an item object.")
        return store.put(master_key, item)
    if action == "reveal":
        context = payload.get("context")
        purpose = payload.get("purpose")
        digest: bytes | None = None
        try:
            digest = store.resource_digest(master_key, payload.get("resource"))
            if (
                payload.get("owner_confirmed") is not True
                or not isinstance(context, dict)
                or context.get("kind") != "private"
            ):
                raise vault_module.VaultError(
                    "OWNER_CONFIRMATION_REQUIRED",
                    "Owner reveal requires explicit confirmation of a private output context.",
                )
            if not isinstance(purpose, str) or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", purpose) is None:
                raise vault_module.VaultError("PURPOSE_REQUIRED", "Vault reveal requires a structured purpose code.")
            result = store.reveal(master_key, payload.get("resource"), payload.get("fields", []))
        except vault_module.VaultError as error:
            try:
                with store.connect() as connection:
                    store.audit(connection, None, "reveal", digest, "denied", error.code, None)
            except (vault_module.VaultError, sqlite3.DatabaseError):
                pass
            raise
        with store.connect() as connection:
            store.audit(
                connection,
                None,
                "reveal",
                digest,
                "allowed",
                "OWNER_CONFIRMED_PRIVATE_CONTEXT",
                None,
            )
        return result
    if action == "rotate-passphrase":
        new_passphrase = payload.get("new_passphrase")
        if not isinstance(new_passphrase, str):
            raise vault_module.VaultError("PASSPHRASE_REQUIRED", "Provide the new passphrase through standard input.")
        store.rotate_passphrase(master_key, new_passphrase)
        return {"ok": True, "rotated": True}
    if action == "rotate-recovery":
        recovery_path = payload.get("recovery_path")
        if not isinstance(recovery_path, str) or not recovery_path:
            raise vault_module.VaultError(
                "RECOVERY_PATH_REQUIRED",
                "Recovery rotation requires an explicit new recovery-file path.",
            )
        selected_recovery = Path(recovery_path).expanduser().resolve()
        if selected_recovery.exists():
            raise vault_module.VaultError("RECOVERY_FILE_EXISTS", "The selected recovery file already exists.")
        recovery_key = vault_module.RECOVERY_PREFIX + vault_module.b64(
            vault_module.crypto().bindings.randombytes(32)
        )
        write_recovery_file(selected_recovery, recovery_key)
        try:
            store.rotate_recovery(master_key, vault_module.recovery_bytes(recovery_key))
        except Exception:
            selected_recovery.unlink(missing_ok=True)
            raise
        return {"ok": True, "rotated": True, "recovery_file": str(selected_recovery)}
    if action == "delete":
        return store.delete(master_key, payload.get("resource"))
    if action == "grant":
        identity = load_identity(root)
        agent_id = payload.get("agent_id", identity["id"])
        scopes = payload.get("scopes", [])
        classes = payload.get("resource_classes", [])
        if not isinstance(scopes, list) or not isinstance(classes, list):
            raise vault_module.VaultError("INVALID_SCOPE", "Scopes and resource classes must be arrays.")
        return vault_module.grant_agent(store, str(agent_id), root, scopes, classes)
    if action == "revoke":
        agent_id = payload.get("agent_id")
        if not isinstance(agent_id, str):
            raise vault_module.VaultError("INVALID_AGENT", "Revoke requires an agent identifier.")
        return vault_module.revoke_agent(store, agent_id)
    if action == "attach":
        operation = payload.get("operation", "add")
        if operation == "add":
            source = payload.get("source")
            if not isinstance(source, str):
                raise vault_module.VaultError("ATTACHMENT_UNREADABLE", "Attach requires an explicit source path.")
            return vault_module.add_attachment(
                store,
                master_key,
                payload.get("resource"),
                Path(source).expanduser().resolve(),
                filename=payload.get("filename") if isinstance(payload.get("filename"), str) else None,
                mime_type=payload.get("mime_type", "application/octet-stream"),
            )
        if operation == "get":
            destination = payload.get("destination")
            if not isinstance(destination, str):
                raise vault_module.VaultError("OUTPUT_REQUIRED", "Attachment retrieval requires an explicit output path.")
            output = Path(destination).expanduser().resolve()
            if output.exists():
                raise vault_module.VaultError("OUTPUT_EXISTS", "Attachment retrieval refuses to overwrite a file.")
            if not output.parent.is_dir():
                raise vault_module.VaultError("OUTPUT_REQUIRED", "The attachment output directory does not exist.")
            descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
            try:
                os.fchmod(descriptor, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    result = vault_module.extract_attachment(store, master_key, str(payload.get("attachment_id")), stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary_name, output)
                result["path"] = str(output)
                return result
            finally:
                Path(temporary_name).unlink(missing_ok=True)
        raise vault_module.VaultError("INVALID_ATTACHMENT_OPERATION", "Attachment operation must be add or get.")
    if action == "export":
        destination = payload.get("destination")
        if not isinstance(destination, str):
            raise vault_module.VaultError("BACKUP_DESTINATION_REQUIRED", "Export requires an explicit destination.")
        return vault_module.export_backup(store, Path(destination).expanduser().resolve())
    if action == "audit":
        limit = payload.get("limit", 100)
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise vault_module.VaultError("INVALID_LIMIT", "Audit limit must be an integer from 1 to 500.")
        return store.audit_list(limit)
    raise vault_module.VaultError("VAULT_ACTION_UNSUPPORTED", "The requested Vault action is unsupported.")


def benchmark_record(root: Path, number: int) -> None:
    memory_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://megabrain.invalid/benchmark/{number}"))
    relevant = number < 8
    subject = f"round6.pricing.family_{number}" if relevant else f"benchmark.unrelated_{number}"
    tags = ["round6", "pricing", "collection"] if relevant else ["unrelated"]
    importance = "normal" if relevant else ("core" if number < 28 else "normal")
    meta = {
        "schema": MEMORY_SCHEMA,
        "id": memory_id,
        "kind": "fact",
        "subject": subject,
        "created_at": "2026-01-01T00:00:00Z",
        "created_by": "00000000-0000-4000-8000-000000000001",
        "confidence": "confirmed",
        "sensitivity": "general",
        "importance": importance,
        "tags": tags,
        "supersedes": [],
        "source": {"type": "agent-observation"},
    }
    path = root / "brain" / "memories" / "2026" / "01" / f"benchmark-{number:05d}-{memory_id}.md"
    summary = f"Synthetic Round 6 pricing family entry {number}." if relevant else f"Synthetic unrelated benchmark memory {number}."
    write_record(path, meta, body_for(meta, summary))


def command_benchmark() -> dict[str, Any]:
    reports: list[dict[str, Any]] = []
    for size in (30, 1_000, 10_000):
        with tempfile.TemporaryDirectory(prefix=f"megabrain-benchmark-{size}-") as temporary:
            root = Path(temporary)
            (root / "brain" / "memories").mkdir(parents=True)
            (root / "brain" / "agents").mkdir()
            (root / "brain" / "imports").mkdir()
            (root / "megabrain.json").write_text(
                json.dumps(
                    {"schema": BRAIN_SCHEMA, "protocol_version": 1, "minimum_runtime": "1.0.0"},
                    indent=2,
                    sort_keys=True,
                ) + "\n",
                encoding="utf-8",
            )
            (root / ".gitignore").write_text(".megabrain/\n", encoding="utf-8")
            run(["git", "init", "--initial-branch=main"], root, check=True)
            run(["git", "config", "user.name", "MegaBrain Benchmark"], root, check=True)
            run(["git", "config", "user.email", "benchmark@example.invalid"], root, check=True)
            for number in range(size):
                benchmark_record(root, number)
            run(["git", "add", "."], root, check=True)
            run(["git", "commit", "-m", "benchmark: fixed synthetic corpus"], root, check=True)
            request = {"task": "Return all Round 6 prices", "diagnostic": True}
            cold = command_context(root, request, 12)
            warm_runs = [command_context(root, request, 12) for _ in range(5)]
            warm_totals = [run_result["diagnostics"]["timings_ms"]["total"] for run_result in warm_runs]
            reports.append(
                {
                    "memories": size,
                    "returned": len(cold["memories"]),
                    "target_collection_complete": len(cold["memories"]) == 8,
                    "cold": cold["diagnostics"],
                    "warm_median_ms": round(statistics.median(warm_totals), 3),
                    "warm_runs_ms": warm_totals,
                    "warm_stage_medians_ms": {
                        stage: round(statistics.median(run_result["diagnostics"]["timings_ms"][stage] for run_result in warm_runs), 3)
                        for stage in warm_runs[0]["diagnostics"]["timings_ms"]
                    },
                }
            )
    return {
        "ok": True,
        "synthetic": True,
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
        },
        "reports": reports,
    }


def automatic_runtime_update() -> dict[str, Any] | None:
    resolved = Path(__file__).resolve()
    runtime_root = Path.home() / ".megabrain" / "runtime"
    if runtime_root not in resolved.parents or not (Path.home() / ".megabrain" / "config.json").exists():
        return None
    checked = subprocess.run(
        [sys.executable, str(resolved.with_name("bootstrap.py")), "update", "--automatic"],
        text=True,
        capture_output=True,
        check=False,
    )
    output = checked.stdout if checked.stdout.strip() else checked.stderr
    try:
        result = json.loads(output)
    except json.JSONDecodeError:
        return {"updated": False, "reason": "update_check_failed"}
    if checked.returncode != 0:
        return {"updated": False, "reason": str(result.get("error", {}).get("code", "update_check_failed")).lower()}
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="megabrain", description="Local-first Markdown brain helper")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("sync")
    context = subparsers.add_parser("context")
    context.add_argument("--stdin", action="store_true", help="read task JSON from stdin")
    context.add_argument("--limit", type=int, default=12)
    remember = subparsers.add_parser("remember")
    remember.add_argument("--stdin", action="store_true")
    correct = subparsers.add_parser("correct")
    correct.add_argument("memory_id")
    correct.add_argument("--stdin", action="store_true")
    forget = subparsers.add_parser("forget")
    forget.add_argument("memory_id")
    forget.add_argument("--stdin", action="store_true")
    ingest = subparsers.add_parser("ingest")
    ingest.add_argument("--stdin", action="store_true")
    subparsers.add_parser("agents")
    browse = subparsers.add_parser("browse")
    browse.add_argument("--no-open", action="store_true", help="generate the browser without opening it")
    subparsers.add_parser("validate")
    subparsers.add_parser("doctor")
    subparsers.add_parser("benchmark")
    vault = subparsers.add_parser("vault")
    vault.add_argument(
        "action",
        choices=(
            "setup", "status", "unlock", "lock", "put", "metadata", "reveal", "attach",
            "export", "restore", "grant", "revoke", "rotate-passphrase", "rotate-recovery",
            "delete", "audit", "doctor", "_serve",
        ),
    )
    vault.add_argument("--stdin", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        runtime_update = automatic_runtime_update() if args.command == "context" else None
        root = repo_root() if args.command != "benchmark" else Path.cwd()
        if args.command == "sync":
            require_compatible_runtime(root, writing=True)
            sync = sync_repo(root)
            result = {"ok": sync.get("reason") != "validation_failed", **sync}
        elif args.command == "context":
            if not 1 <= args.limit <= 100:
                raise BrainError("INVALID_LIMIT", "limit must be between 1 and 100")
            result = command_context(root, read_input(), args.limit)
        elif args.command == "remember":
            result = command_remember(root, read_input())
        elif args.command == "correct":
            result = command_correct(root, args.memory_id, read_input())
        elif args.command == "forget":
            result = command_forget(root, args.memory_id, read_input(required=False))
        elif args.command == "ingest":
            result = command_ingest(root, read_input())
        elif args.command == "agents":
            result = command_agents(root)
        elif args.command == "browse":
            result = command_browse(root, args.no_open)
        elif args.command == "validate":
            result = command_validate(root)
        elif args.command == "doctor":
            result = command_doctor(root)
        elif args.command == "vault":
            result = command_vault(root, args.action, read_input(required=False))
        elif args.command == "benchmark":
            result = command_benchmark()
        else:
            parser.error("unknown command")
            return 2
        if runtime_update and (
            runtime_update.get("updated")
            or runtime_update.get("approval_required")
            or runtime_update.get("stale")
        ):
            result["runtime_update"] = runtime_update
        emit(result)
        return 0 if result.get("ok", False) else 1
    except BrainError as error:
        emit({"ok": False, "error": {"code": error.code, "message": error.message, "details": error.details}}, stream=sys.stderr)
        return 2
    except vault_module.VaultError as error:
        emit({"ok": False, "error": {"code": error.code, "message": error.message, "details": error.details}}, stream=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
