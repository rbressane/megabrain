#!/usr/bin/env python3
"""Owner-run, review-first inventory and candidate preparation.

This utility is intentionally separate from the active MegaBrain runtime. It
reads only explicitly allowlisted files and never commits or imports anything.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import stat
import sys
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import canonical
import megabrain


MAX_FILES = 1_000
MAX_FILE_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 10 * 1024 * 1024
EXCLUDED_NAMES = {"agents.md", "claude.md", "memory.md", "user.md"}
EXCLUDED_PARTS = {"persona", "personas", "prompt", "prompts", "template", "templates", "session", "sessions", "journal", "journals"}


def _under(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_relative(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise canonical.CanonicalError("SOURCE_PATH_INVALID", "Allowlisted source path is invalid")
    if any(unicodedata.category(character).startswith("C") for character in normalized):
        raise canonical.CanonicalError("SOURCE_PATH_INVALID", "Allowlisted source path contains unsafe Unicode")
    return str(pure)


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    lines = text.splitlines()
    try:
        end = lines[1:101].index("---") + 1
    except ValueError as error:
        raise canonical.CanonicalError("FRONTMATTER_INVALID", "Markdown frontmatter is not terminated") from error
    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise canonical.CanonicalError("FRONTMATTER_INVALID", "Markdown frontmatter must use key: value lines")
        key, value = line.split(":", 1)
        key = key.strip()
        if not key or key in metadata:
            raise canonical.CanonicalError("FRONTMATTER_INVALID", "Markdown frontmatter keys must be unique")
        metadata[key] = value.strip()
    return metadata, "\n".join(lines[end + 1 :])


def _excluded(relative: str) -> str | None:
    pure = PurePosixPath(relative)
    lowered = {part.casefold() for part in pure.parts}
    if pure.name.casefold() in EXCLUDED_NAMES:
        return "excluded-instruction"
    matched = lowered & EXCLUDED_PARTS
    if "template" in matched or "templates" in matched:
        return "excluded-template"
    if "persona" in matched or "personas" in matched:
        return "excluded-persona"
    if matched:
        return "excluded-transcript"
    return None


def inventory(
    source_root: Path,
    allowlist: Iterable[str],
    *,
    denylist: Iterable[str] = (),
) -> dict[str, Any]:
    root = source_root.expanduser().resolve()
    state = os.lstat(root)
    if stat.S_ISLNK(state.st_mode) or not stat.S_ISDIR(state.st_mode):
        raise canonical.CanonicalError("SOURCE_ROOT_UNSAFE", "Source root is missing or unsafe")
    allowed = [_safe_relative(value) for value in allowlist]
    if not 1 <= len(allowed) <= MAX_FILES:
        raise canonical.CanonicalError("SOURCE_LIMIT_EXCEEDED", "Allowlist must contain 1 to 1000 files")
    skeletons = [unicodedata.normalize("NFKC", value).casefold() for value in allowed]
    if len(set(skeletons)) != len(skeletons):
        raise canonical.CanonicalError("SOURCE_PATH_CONFUSABLE", "Allowlist contains Unicode-confusable paths")
    denied = list(denylist)
    coverage = []
    candidates = []
    total = 0
    for relative in sorted(allowed):
        locator = f"file-relative://{relative}"
        if any(fnmatch.fnmatch(relative, pattern) for pattern in denied):
            coverage.append({"locator": locator, "status": "intentionally-skipped", "fingerprint": None, "reason": "denylist"})
            continue
        path = root / relative
        try:
            unresolved = path.absolute()
            resolved = path.resolve(strict=True)
            file_state = os.lstat(unresolved)
            if stat.S_ISLNK(file_state.st_mode) or not stat.S_ISREG(file_state.st_mode) or not _under(root, resolved):
                raise OSError("unsafe path")
            content = resolved.read_bytes()
        except OSError:
            coverage.append({"locator": locator, "status": "rejected", "fingerprint": None, "reason": "missing-or-unsafe"})
            continue
        if len(content) > MAX_FILE_BYTES:
            coverage.append({"locator": locator, "status": "rejected", "fingerprint": None, "reason": "oversized"})
            continue
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            raise canonical.CanonicalError("SOURCE_LIMIT_EXCEEDED", "Expanded source size exceeds 10 MiB")
        fingerprint = canonical.fingerprint_bytes(content)
        exclusion = _excluded(relative)
        if exclusion:
            coverage.append({"locator": locator, "status": exclusion, "fingerprint": fingerprint, "reason": "excluded-class"})
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            coverage.append({"locator": locator, "status": "rejected", "fingerprint": fingerprint, "reason": "invalid-utf8"})
            continue
        if megabrain.detect_secret(text):
            coverage.append({"locator": locator, "status": "sensitive-deferred", "fingerprint": fingerprint, "reason": "secret-like"})
            continue
        try:
            frontmatter, body = _frontmatter(text)
        except canonical.CanonicalError:
            coverage.append({"locator": locator, "status": "rejected", "fingerprint": fingerprint, "reason": "malformed-frontmatter"})
            continue
        title = frontmatter.get("title") or next(
            (line.removeprefix("#").strip() for line in body.splitlines() if line.startswith("# ")),
            Path(relative).stem,
        )
        resource_type = frontmatter.get("resource_type", "document")
        if resource_type not in canonical.RESOURCE_TYPES:
            resource_type = "document"
        candidate_id = str(canonical.uuid.uuid5(canonical.uuid.NAMESPACE_URL, f"megabrain-import:{locator}:{fingerprint}"))
        candidate = {
            "candidate_id": candidate_id,
            "kind": "resource",
            "source_locator": locator,
            "source_fingerprint": fingerprint,
            "data": {
                "resource_type": resource_type,
                "title": title,
                "owner": frontmatter.get("owner", "owner"),
                "authority_domain": frontmatter.get("authority_domain", "personal"),
                "sensitivity": frontmatter.get("sensitivity", "general"),
                "source_at": frontmatter.get("source_at"),
                "verified_at": frontmatter.get("verified_at"),
                "freshness_at": frontmatter.get("freshness_at"),
                "body": body,
            },
        }
        candidates.append(candidate)
        coverage.append({"locator": locator, "status": "candidate-extracted", "fingerprint": fingerprint, "reason": ""})
    return {
        "schema": "megabrain.prepared-inventory.v1",
        "source_root_fingerprint": canonical.fingerprint_bytes(str(root).encode("utf-8")),
        "source_type": "filesystem",
        "source_locator": f"prepared-source://{canonical.fingerprint_bytes(str(root).encode('utf-8')).removeprefix('sha256:')}",
        "coverage": coverage,
        "candidates": candidates,
        "counts": {
            "allowlisted": len(allowed),
            "candidates": len(candidates),
            "by_status": dict(sorted(Counter(item["status"] for item in coverage).items())),
        },
    }


def write_private(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=True, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
        os.chmod(path, 0o600)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prepare-import")
    parser.add_argument("--source", required=True)
    parser.add_argument("--allow", action="append", required=True)
    parser.add_argument("--deny", action="append", default=[])
    parser.add_argument("--output", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise canonical.CanonicalError(
                "OWNER_LOCAL_CONTROL_REQUIRED",
                "Run source preparation in an owner-local interactive terminal",
            )
        result = inventory(Path(args.source), args.allow, denylist=args.deny)
        output = Path(args.output).expanduser().resolve()
        source = Path(args.source).expanduser().resolve()
        if output == source or source in output.parents:
            raise canonical.CanonicalError("OUTPUT_PATH_INVALID", "Prepared output must stay outside the source")
        write_private(output, result)
        summary = {
            "ok": True,
            "output": str(output),
            "fingerprint": canonical.fingerprint_bytes(canonical.canonical_json(result)),
            "counts": result["counts"],
        }
        megabrain.emit(summary)
        return 0
    except canonical.CanonicalError as error:
        megabrain.emit({"ok": False, "error": {"code": error.code, "message": error.message}}, stream=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
