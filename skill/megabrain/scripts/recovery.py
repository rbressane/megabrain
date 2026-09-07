"""Owner-reviewed, offline Git bundle backup and restore. Never replaces a clone."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile

import operations


def backup(root: Path, destination: Path) -> dict:
    destination = destination.expanduser().absolute()
    if destination.exists() or destination.is_symlink() or root.resolve() in destination.resolve().parents:
        raise operations.OperationError("BACKUP_DESTINATION_INVALID", "Choose a new backup file outside the Brain.")
    if operations.git_text(root, "status", "--porcelain"):
        raise operations.OperationError("CLONE_DIRTY", "Commit or review local edits before backing up. Nothing was changed.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".megabrain-backup-", dir=destination.parent) as directory:
        bundle = Path(directory) / "brain.bundle"
        result = operations.run(["git", "bundle", "create", str(bundle), "--all"], root)
        if result.returncode or operations.run(["git", "bundle", "verify", str(bundle)], root).returncode:
            raise operations.OperationError("BACKUP_FAILED", "The backup could not be verified.")
        os.chmod(bundle, 0o600)
        with bundle.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(stream.read()).hexdigest()
        os.link(bundle, destination)
    return {"ok": True, "commit": operations.git_text(root, "rev-parse", "HEAD"), "sha256": digest,
            "warning": "Private plaintext backup includes Git history. Protect it like the Brain."}


def restore(bundle: Path, destination: Path, expected_sha256: str) -> dict:
    bundle, destination = bundle.expanduser().resolve(), destination.expanduser().absolute()
    if not bundle.is_file() or hashlib.sha256(bundle.read_bytes()).hexdigest() != expected_sha256:
        raise operations.OperationError("BACKUP_HASH_MISMATCH", "The backup does not match its owner-held SHA-256 receipt.")
    if destination.exists() or destination.is_symlink():
        raise operations.OperationError("RESTORE_DESTINATION_EXISTS", "Restore requires a new directory. No existing clone was changed.")
    destination.mkdir(parents=True, mode=0o700)
    cloned = operations.run(["git", "clone", str(bundle), str(destination)])
    if cloned.returncode or operations.run(["git", "fsck", "--full"], destination).returncode:
        raise operations.OperationError("RESTORE_FAILED", "The new recovery directory needs inspection. Existing clones were not changed.")
    from megabrain import command_validate
    if not command_validate(destination)["ok"]:
        raise operations.OperationError("RESTORE_INVALID", "The recovered Brain failed validation. Do not connect it.")
    operations.run(["git", "remote", "remove", "origin"], destination)
    return {"ok": True, "commit": operations.git_text(destination, "rev-parse", "HEAD"),
            "connected": False, "notice": "Recovery verified offline. Existing agents and clones were not changed."}
