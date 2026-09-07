"""Bounded processes, private files, clone transactions and committed snapshots.

These are accidental-damage guardrails, not a sandbox against the filesystem owner.
"""
from __future__ import annotations

import contextlib
import contextvars
import fcntl
import functools
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tarfile
import tempfile
import time
from typing import Any, Callable, Iterator

PROCESS_TIMEOUT = 30
LOCK_TIMEOUT = 10
MAX_BLOB_BYTES = 64 * 1024 * 1024
IMMUTABLE_PREFIXES = ("brain/memories/", "brain/resources/", "brain/policies/", "brain/imports/", "brain/attachments/")
_HELD: contextvars.ContextVar[frozenset[str]] = contextvars.ContextVar("megabrain_locks", default=frozenset())


class OperationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message, self.details = code, message, {}


def run(command: list[str], cwd: Path | None = None, *, env: dict[str, str] | None = None,
        timeout: float = PROCESS_TIMEOUT, text: bool = True) -> subprocess.CompletedProcess:
    environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never", **(env or {})}
    process = subprocess.Popen(command, cwd=cwd, env=environment, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=text, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        empty = "" if text else b""
        return subprocess.CompletedProcess(command, 124, empty, empty)
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def private_directory(path: Path) -> None:
    if path.is_symlink():
        raise OperationError("UNSAFE_LOCAL_PATH", "A private state directory cannot be a symlink.")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)


def atomic_write(path: Path, content: str | bytes, *, exclusive: bool = False) -> None:
    private_directory(path.parent)
    if path.is_symlink():
        raise OperationError("UNSAFE_LOCAL_PATH", "A private output cannot be a symlink.")
    descriptor, name = tempfile.mkstemp(prefix=".megabrain-write-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content.encode("utf-8") if isinstance(content, str) else content)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            os.link(temporary, path)  # atomic create-if-absent, never replace an immutable record
        else:
            os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


@contextlib.contextmanager
def lock(root: Path, *, name: str = "operation", timeout: float = LOCK_TIMEOUT) -> Iterator[None]:
    path = root / ".megabrain" / f"{name}.lock"
    key = str(path.resolve())
    held = _HELD.get()
    if key in held:
        yield
        return
    private_directory(path.parent)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise OperationError("BRAIN_BUSY", "Another Brain operation is running. Retry shortly.")
                time.sleep(0.05)
        token = _HELD.set(held | {key})
        try:
            yield
        finally:
            _HELD.reset(token)
    finally:
        os.close(descriptor)


def locked(function: Callable) -> Callable:
    @functools.wraps(function)
    def wrapped(root: Path, *args: Any, **kwargs: Any) -> Any:
        with lock(root):
            return function(root, *args, **kwargs)
    return wrapped


def git_text(root: Path, *args: str) -> str:
    result = run(["git", *args], root)
    if result.returncode:
        raise OperationError("GIT_UNAVAILABLE", "Git could not complete the operation. Local data was retained.")
    return result.stdout.strip()


@contextlib.contextmanager
def snapshot(root: Path, *paths: str, commit: str | None = None) -> Iterator[Path]:
    commit = commit or git_text(root, "rev-parse", "HEAD")
    state = root / ".megabrain"
    private_directory(state)
    with tempfile.TemporaryDirectory(prefix="snapshot-", dir=state) as directory:
        destination = Path(directory)
        archive_path = destination / "snapshot.tar"
        archived = run(["git", "archive", "--format=tar", "-o", str(archive_path), commit, "--", *paths], root)
        if archived.returncode:
            raise OperationError("SNAPSHOT_FAILED", "The committed snapshot could not be read.")
        with tarfile.open(archive_path) as archive:
            for member in archive:
                relative = Path(member.name)
                if relative.is_absolute() or ".." in relative.parts or not (member.isdir() or member.isfile()):
                    raise OperationError("SNAPSHOT_UNSAFE", "The committed snapshot contains an unsafe entry.")
                target = destination / relative
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True, mode=0o700)
                else:
                    stream = archive.extractfile(member)
                    if stream is None or member.size > MAX_BLOB_BYTES:
                        raise OperationError("SNAPSHOT_UNSAFE", "A snapshot object exceeds safe limits.")
                    atomic_write(target, stream.read(), exclusive=True)
        archive_path.unlink()
        yield destination


def approve_revert(root: Path, target: str, commit: str) -> None:
    """Record only an exact one-commit inverse after the owner-local approval gate."""
    if git_text(root, "rev-parse", f"{commit}^") != target or (
        git_text(root, "rev-parse", f"{commit}^{{tree}}") != git_text(root, "rev-parse", f"{target}^^{{tree}}")
    ):
        raise OperationError("ROLLBACK_NOT_EXACT", "Only an exact inverse of the reviewed latest commit can be approved.")
    atomic_write(root / ".megabrain" / "approved-reverts" / f"{commit}.json", json.dumps({"target": target, "commit": commit}))


def _approved_revert(root: Path, commit: str) -> bool:
    path = root / ".megabrain" / "approved-reverts" / f"{commit}.json"
    try:
        value = json.loads(path.read_text())
        target = value["target"]
        return value["commit"] == commit and git_text(root, "rev-parse", f"{commit}^") == target and (
            git_text(root, "rev-parse", f"{commit}^{{tree}}") == git_text(root, "rev-parse", f"{target}^^{{tree}}")
        )
    except (OSError, ValueError, KeyError, OperationError):
        return False


def outgoing_guard(root: Path, detect_secret: Callable[[Any], Any]) -> str | None:
    """Check ALL outgoing commits, including blobs removed again before HEAD.

    Receipts are rebuildable local state. No secret values or paths enter errors.
    """
    remote = run(["git", "rev-parse", "--verify", "origin/main"], root)
    revision_range = f"{remote.stdout.strip()}..HEAD" if remote.returncode == 0 else "HEAD"
    commits = git_text(root, "rev-list", "--reverse", revision_range).splitlines()
    seen: set[str] = set()
    for commit in commits:
        if len(git_text(root, "rev-list", "--parents", "-n", "1", commit).split()) > 2:
            return "outgoing_merge_requires_review"
        if detect_secret(git_text(root, "show", "-s", "--format=%B", commit)):
            return "outgoing_secret_rejected"
        changes = run(["git", "diff-tree", "--root", "-r", "--no-renames", "--no-commit-id", "--raw", "-z", commit], root)
        if changes.returncode:
            return "outgoing_history_unavailable"
        parts = changes.stdout.split("\0")
        approved = _approved_revert(root, commit)
        for index in range(0, len(parts) - 1, 2):
            header, path = parts[index], parts[index + 1]
            fields = header.split()
            if len(fields) != 5:
                return "outgoing_history_unavailable"
            old_mode, new_mode, old_oid, new_oid, status = fields
            if status != "A" and path.startswith(IMMUTABLE_PREFIXES) and not path.endswith("/.gitkeep") and not approved:
                return "immutable_history_rejected"
            if new_mode == "000000":
                continue
            if new_mode != "100644":
                return "unsafe_git_object_rejected"
            if detect_secret(path):
                return "outgoing_secret_rejected"
            if new_oid in seen:
                continue
            seen.add(new_oid)
            size = int(git_text(root, "cat-file", "-s", new_oid))
            if size > MAX_BLOB_BYTES:
                return "outgoing_object_too_large"
            blob = run(["git", "cat-file", "blob", new_oid], root, text=False)
            if blob.returncode:
                return "outgoing_history_unavailable"
            if detect_secret(blob.stdout.decode("utf-8", errors="replace")):
                return "outgoing_secret_rejected"
    return None
