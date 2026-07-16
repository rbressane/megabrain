"""Canonical durable-resource, migration, policy, and projection primitives.

This module is standard-library only. Imported documents are untrusted data.
Approval helpers accept already-structured candidates and never crawl sources.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import subprocess
import tarfile
import tempfile
import time
import unicodedata
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


RESOURCE_SCHEMA = "megabrain.resource.v1"
ATTACHMENT_SCHEMA = "megabrain.attachment-manifest.v1"
POLICY_SCHEMA = "megabrain.access-policy.v1"
CANDIDATE_SCHEMA = "megabrain.import-candidates.v1"
COVERAGE_SCHEMA = "megabrain.coverage.v1"
RESOURCE_TYPES = {
    "context": "contexts",
    "project": "projects",
    "runbook": "runbooks",
    "decision": "decisions",
    "finding": "findings",
    "document": "documents",
    "archive": "archives",
}
SENSITIVITIES = {"general", "private", "sensitive"}
REVIEW_STATES = {"approved"}
LIFECYCLES = {"active", "retired"}
CAPABILITIES = {"read", "propose", "correct", "retire", "administer"}
SOURCE_TYPES = {"user-statement", "agent-observation", "import", "archive"}
COVERAGE_STATUSES = {
    "discovered",
    "scanned",
    "candidate-extracted",
    "intentionally-skipped",
    "excluded-instruction",
    "excluded-persona",
    "excluded-template",
    "excluded-transcript",
    "sensitive-deferred",
    "canonical-not-scanned",
    "imported",
    "duplicate",
    "conflict",
    "rejected",
    "acceptance-tested",
}
ACCESS_LEVEL = {"general": 0, "private": 1, "sensitive": 2}
MAX_IMPORT_CANDIDATES = 10
MAX_IMPORT_BYTES = 2 * 1024 * 1024
MAX_RESOURCE_BYTES = 512 * 1024
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
RESOURCE_INDEX_SCHEMA = "megabrain.resource-index.v1"
RESOURCE_PATTERN = re.compile(
    r"\A<!--\s*megabrain-resource\s*\n(?P<meta>.*?)\n-->\s*\n?(?P<body>.*)\Z",
    re.DOTALL,
)
CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
SHA256_PATTERN = re.compile(r"^(?:sha256:)?[a-f0-9]{64}$", re.I)
INSTRUCTION_PATTERNS = (
    re.compile(r"ignore (?:all |any )?(?:previous|prior) instructions", re.I),
    re.compile(r"(?:system|developer) prompt", re.I),
    re.compile(r"execute (?:this|the following) command", re.I),
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.I),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(
        r"\b(?:password|passwd|api[_ -]?key|access[_ -]?token|session[_ -]?cookie|recovery[_ -]?code)\s*[:=]\s*\S+",
        re.I,
    ),
    re.compile(r"\b(?:postgres|mysql|mongodb(?:\+srv)?|redis)://[^\s/@:]+:[^\s/@]+@", re.I),
)


class CanonicalError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class ResourceRevision:
    path: Path
    meta: dict[str, Any]
    body: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def valid_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def valid_timestamp(value: Any, *, nullable: bool = False) -> bool:
    if nullable and value is None:
        return True
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def contains_secret_like(value: Any) -> bool:
    return any(pattern.search(text) for text in _strings(value) for pattern in SECRET_PATTERNS)


def normalized_markdown(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    return "\n".join(lines).strip() + ("\n" if any(line.strip() for line in lines) else "")


def fingerprint_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def content_fingerprint(value: str) -> str:
    return fingerprint_bytes(normalized_markdown(value).encode("utf-8"))


def safe_title(value: Any) -> str:
    if not isinstance(value, str):
        raise CanonicalError("RESOURCE_TITLE_INVALID", "Resource title must be text")
    title = unicodedata.normalize("NFC", value).strip()
    if (
        not title
        or len(title) > 200
        or CONTROL_PATTERN.search(title)
        or any(unicodedata.category(character).startswith("C") for character in title)
    ):
        raise CanonicalError("RESOURCE_TITLE_INVALID", "Resource title is invalid")
    return title


def safe_locator(value: Any) -> str:
    if not isinstance(value, str):
        raise CanonicalError("SOURCE_LOCATOR_INVALID", "Source locator must be text")
    locator = unicodedata.normalize("NFC", value).strip()
    if (
        not locator
        or len(locator) > 1024
        or CONTROL_PATTERN.search(locator)
        or any(unicodedata.category(character).startswith("C") for character in locator)
    ):
        raise CanonicalError("SOURCE_LOCATOR_INVALID", "Source locator is invalid")
    if locator.startswith(("/", "~")) or ".." in PurePosixPath(locator).parts:
        raise CanonicalError("SOURCE_LOCATOR_INVALID", "Source locator must not escape its declared source")
    return locator


def resource_uri(resource_id: str) -> str:
    return f"megabrain://resource/{resource_id}"


def resource_path(root: Path, meta: Mapping[str, Any]) -> Path:
    directory = RESOURCE_TYPES[str(meta["resource_type"])]
    return (
        root
        / "brain"
        / "resources"
        / directory
        / str(meta["resource_id"])
        / f"{meta['revision_id']}.md"
    )


def resource_files(root: Path) -> list[Path]:
    base = root / "brain" / "resources"
    return sorted(path for path in base.glob("*/*/*.md") if path.is_file())


def parse_resource(path: Path) -> ResourceRevision:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise CanonicalError("RESOURCE_INVALID", "Resource is not readable UTF-8 data") from error
    match = RESOURCE_PATTERN.match(text)
    if not match:
        raise CanonicalError("RESOURCE_INVALID", "Resource metadata block is missing")
    try:
        meta = json.loads(match.group("meta"))
    except json.JSONDecodeError as error:
        raise CanonicalError("RESOURCE_INVALID", "Resource metadata is invalid JSON") from error
    if not isinstance(meta, dict):
        raise CanonicalError("RESOURCE_INVALID", "Resource metadata must be an object")
    return ResourceRevision(path=path, meta=meta, body=normalized_markdown(match.group("body")))


def write_resource(path: Path, meta: Mapping[str, Any], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = json.dumps(dict(meta), ensure_ascii=True, sort_keys=True, indent=2)
    normalized = normalized_markdown(body)
    suffix = f"\n{normalized}" if normalized else ""
    path.write_text(f"<!-- megabrain-resource\n{metadata}\n-->\n{suffix}", encoding="utf-8")


def validate_resource(record: ResourceRevision) -> list[str]:
    meta = record.meta
    errors: list[str] = []
    required = {
        "schema",
        "schema_version",
        "resource_id",
        "revision_id",
        "uri",
        "resource_type",
        "title",
        "owner",
        "authority_domain",
        "sensitivity",
        "created_at",
        "source_at",
        "verified_at",
        "freshness_at",
        "source",
        "created_by",
        "proposed_by",
        "review_state",
        "lifecycle",
        "supersedes_revision",
        "content_fingerprint",
        "attachment_manifest",
        "import_batch",
    }
    if set(meta) != required:
        errors.append("resource metadata fields are not exact")
    if meta.get("schema") != RESOURCE_SCHEMA or meta.get("schema_version") != 1:
        errors.append("invalid resource schema")
    if not valid_uuid(meta.get("resource_id")) or not valid_uuid(meta.get("revision_id")):
        errors.append("resource and revision IDs must be UUIDs")
    if meta.get("uri") != resource_uri(str(meta.get("resource_id"))):
        errors.append("resource URI does not match resource ID")
    if meta.get("resource_type") not in RESOURCE_TYPES:
        errors.append("invalid resource type")
    try:
        safe_title(meta.get("title"))
    except CanonicalError:
        errors.append("invalid display title")
    for field in ("owner", "authority_domain"):
        if not isinstance(meta.get(field), str) or not meta[field].strip() or CONTROL_PATTERN.search(meta[field]):
            errors.append(f"{field} is invalid")
    if meta.get("sensitivity") not in SENSITIVITIES:
        errors.append("invalid sensitivity")
    if not valid_timestamp(meta.get("created_at")):
        errors.append("created_at must be a UTC timestamp")
    for field in ("source_at", "verified_at", "freshness_at"):
        if not valid_timestamp(meta.get(field), nullable=True):
            errors.append(f"{field} must be null or a UTC timestamp")
    source = meta.get("source")
    if (
        not isinstance(source, dict)
        or set(source) != {"type", "locator", "fingerprint"}
        or source.get("type") not in SOURCE_TYPES
        or not isinstance(source.get("locator"), str)
        or not SHA256_PATTERN.fullmatch(str(source.get("fingerprint", "")))
    ):
        errors.append("source must contain type, safe locator, and SHA-256 fingerprint")
    else:
        try:
            safe_locator(source["locator"])
        except CanonicalError:
            errors.append("source locator is invalid")
    for field in ("created_by", "proposed_by"):
        if not valid_uuid(meta.get(field)):
            errors.append(f"{field} must be an agent UUID")
    if meta.get("review_state") not in REVIEW_STATES:
        errors.append("resource is not approved")
    if meta.get("lifecycle") not in LIFECYCLES:
        errors.append("invalid lifecycle")
    supersedes = meta.get("supersedes_revision")
    if supersedes is not None and not valid_uuid(supersedes):
        errors.append("supersedes_revision must be null or a UUID")
    if not SHA256_PATTERN.fullmatch(str(meta.get("content_fingerprint", ""))):
        errors.append("content fingerprint must be SHA-256")
    elif meta.get("content_fingerprint") != content_fingerprint(record.body):
        errors.append("content fingerprint does not match normalized Markdown")
    attachment = meta.get("attachment_manifest")
    if attachment is not None and not valid_uuid(attachment):
        errors.append("attachment manifest must be null or a UUID")
    if meta.get("import_batch") is not None and not valid_uuid(meta.get("import_batch")):
        errors.append("import batch must be null or a UUID")
    if meta.get("sensitivity") == "sensitive" and (record.body or attachment is not None):
        errors.append("sensitive synchronized content is unavailable pending security review")
    if len(record.body.encode("utf-8")) > MAX_RESOURCE_BYTES:
        errors.append("resource body exceeds the size limit")
    if contains_secret_like({"meta": meta, "body": record.body}):
        errors.append("resource contains possible secret material")
    return errors


def load_resources(root: Path) -> list[ResourceRevision]:
    return [parse_resource(path) for path in resource_files(root)]


def current_resources(
    records: Iterable[ResourceRevision],
) -> tuple[list[ResourceRevision], dict[str, list[str]]]:
    items = list(records)
    superseded = {
        str(record.meta["supersedes_revision"])
        for record in items
        if record.meta.get("supersedes_revision")
    }
    active = [
        record
        for record in items
        if str(record.meta.get("revision_id")) not in superseded
        and record.meta.get("lifecycle") != "retired"
    ]
    by_resource: dict[str, list[ResourceRevision]] = defaultdict(list)
    for record in active:
        by_resource[str(record.meta.get("resource_id"))].append(record)
    conflicts = {
        resource_id: [str(item.meta["revision_id"]) for item in records]
        for resource_id, records in by_resource.items()
        if len(records) > 1
    }
    return active, conflicts


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))


def resource_index_path(root: Path) -> Path:
    return root / ".megabrain" / "resource-index.sqlite3"


def _git_commit(root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def build_resource_index(root: Path, commit: str, path: Path) -> float:
    started = time.perf_counter()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix=".resource-tree-", dir=path.parent) as tree_name:
        snapshot = Path(tree_name)
        archived = subprocess.Popen(
            ["git", "archive", "--format=tar", commit, "--", "brain/resources"],
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
                        raise CanonicalError("RESOURCE_INDEX_INVALID", "Committed resource archive is unsafe")
                    archive.extract(member, snapshot, filter="data")
        except Exception:
            archived.kill()
            archived.wait()
            raise
        finally:
            archived.stdout.close()
        stderr = archived.stderr.read().decode("utf-8", errors="replace") if archived.stderr else ""
        if archived.stderr:
            archived.stderr.close()
        if archived.wait() != 0:
            raise CanonicalError("RESOURCE_INDEX_FAILED", "Committed resources could not be indexed", {"git": stderr[-300:]})
        current, conflicts = current_resources(load_resources(snapshot))
        descriptor, temporary_name = tempfile.mkstemp(prefix=".resource-index-", dir=path.parent)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            connection = sqlite3.connect(temporary)
            connection.executescript(
                """
                PRAGMA journal_mode=OFF;
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE resources (
                    revision_id TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    meta_json TEXT NOT NULL,
                    body TEXT NOT NULL
                );
                CREATE TABLE postings (
                    token TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    PRIMARY KEY(token, revision_id)
                );
                CREATE TABLE conflicts (
                    resource_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    PRIMARY KEY(resource_id, revision_id)
                );
                """
            )
            connection.executemany(
                "INSERT INTO metadata VALUES (?, ?)",
                (("schema", RESOURCE_INDEX_SCHEMA), ("commit", commit)),
            )
            for record in current:
                revision_id = str(record.meta["revision_id"])
                connection.execute(
                    "INSERT INTO resources VALUES (?, ?, ?, ?)",
                    (
                        revision_id,
                        str(record.path.relative_to(snapshot)),
                        json.dumps(record.meta, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
                        record.body,
                    ),
                )
                searchable = f"{record.meta['title']} {record.meta['resource_type']} {record.body}"
                connection.executemany(
                    "INSERT INTO postings VALUES (?, ?)",
                    ((token, revision_id) for token in _tokens(searchable)),
                )
            connection.executemany(
                "INSERT INTO conflicts VALUES (?, ?)",
                ((resource_id, revision_id) for resource_id, revisions in conflicts.items() for revision_id in revisions),
            )
            connection.commit()
            connection.close()
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    return time.perf_counter() - started


def open_resource_index(
    root: Path,
    *,
    allow_rebuild: bool = True,
) -> tuple[sqlite3.Connection, str, float]:
    started = time.perf_counter()
    commit = _git_commit(root)
    if not commit:
        raise CanonicalError("RESOURCE_INDEX_UNAVAILABLE", "Resource indexing requires a Git commit")
    path = resource_index_path(root)
    if not path.exists() and not allow_rebuild:
        raise CanonicalError("DIRTY_RESOURCE_INDEX_UNAVAILABLE", "Uncommitted resources will not be indexed")
    connection: sqlite3.Connection | None = None
    state = "warm"
    try:
        connection = sqlite3.connect(path)
        metadata = dict(connection.execute("SELECT key,value FROM metadata"))
        if metadata != {"schema": RESOURCE_INDEX_SCHEMA, "commit": commit}:
            raise sqlite3.DatabaseError("stale index")
    except (OSError, sqlite3.DatabaseError):
        if connection is not None:
            connection.close()
        path.unlink(missing_ok=True)
        if not allow_rebuild:
            raise CanonicalError("DIRTY_RESOURCE_INDEX_UNAVAILABLE", "Uncommitted resources will not be indexed")
        elapsed = build_resource_index(root, commit, path)
        connection = sqlite3.connect(path)
        state = "cold"
        return connection, state, elapsed
    assert connection is not None
    return connection, state, time.perf_counter() - started


def _indexed_resource(root: Path, row: tuple[Any, ...]) -> ResourceRevision:
    return ResourceRevision(path=root / str(row[1]), meta=json.loads(row[2]), body=str(row[3]))


def search_resources(
    root: Path,
    query_tokens: set[str],
    *,
    allow_rebuild: bool = True,
) -> tuple[list[ResourceRevision], dict[str, list[str]], str, float]:
    connection, state, elapsed = open_resource_index(root, allow_rebuild=allow_rebuild)
    try:
        if query_tokens:
            placeholders = ",".join("?" for _ in query_tokens)
            revision_ids = [
                row[0]
                for row in connection.execute(
                    f"SELECT revision_id FROM postings WHERE token IN ({placeholders}) GROUP BY revision_id HAVING COUNT(DISTINCT token) = ?",  # nosec B608
                    [*sorted(query_tokens), len(query_tokens)],
                )
            ]
        else:
            revision_ids = [row[0] for row in connection.execute("SELECT revision_id FROM resources")]
        records = []
        if revision_ids:
            placeholders = ",".join("?" for _ in revision_ids)
            records = [
                _indexed_resource(root, row)
                for row in connection.execute(
                    f"SELECT revision_id,path,meta_json,body FROM resources WHERE revision_id IN ({placeholders})",  # nosec B608
                    sorted(revision_ids),
                )
            ]
        conflicts: dict[str, list[str]] = defaultdict(list)
        for resource_id, revision_id in connection.execute("SELECT resource_id,revision_id FROM conflicts"):
            conflicts[resource_id].append(revision_id)
        return records, dict(conflicts), state, elapsed
    finally:
        connection.close()


def read_indexed_resource(
    root: Path,
    reference: str,
    *,
    allow_rebuild: bool = True,
) -> tuple[ResourceRevision, str, float]:
    resource_id = reference.removeprefix("megabrain://resource/")
    if not valid_uuid(resource_id):
        raise CanonicalError("RESOURCE_URI_INVALID", "Resource reference must be a megabrain:// URI or UUID")
    connection, state, elapsed = open_resource_index(root, allow_rebuild=allow_rebuild)
    try:
        rows = list(connection.execute(
            "SELECT revision_id,path,meta_json,body FROM resources WHERE json_extract(meta_json, '$.resource_id')=?",
            (resource_id,),
        ))
    finally:
        connection.close()
    if len(rows) != 1:
        raise CanonicalError("RESOURCE_NOT_FOUND", "Current resource was not found")
    return _indexed_resource(root, rows[0]), state, elapsed


def find_resource(root: Path, reference: str) -> tuple[ResourceRevision, bool]:
    resource_id = reference.removeprefix("megabrain://resource/")
    if not valid_uuid(resource_id):
        raise CanonicalError("RESOURCE_URI_INVALID", "Resource reference must be a megabrain:// URI or UUID")
    records = load_resources(root)
    current, _ = current_resources(records)
    matches = [record for record in current if record.meta.get("resource_id") == resource_id]
    if len(matches) != 1:
        raise CanonicalError("RESOURCE_NOT_FOUND", "Current resource was not found")
    return matches[0], True


def resource_metadata(record: ResourceRevision) -> dict[str, Any]:
    return {
        "uri": record.meta["uri"],
        "resource_id": record.meta["resource_id"],
        "revision_id": record.meta["revision_id"],
        "resource_type": record.meta["resource_type"],
        "title": record.meta["title"],
        "sensitivity": record.meta["sensitivity"],
        "owner": record.meta["owner"],
        "authority_domain": record.meta["authority_domain"],
        "verified_at": record.meta["verified_at"],
        "freshness_at": record.meta["freshness_at"],
        "lifecycle": record.meta["lifecycle"],
        "content_fingerprint": record.meta["content_fingerprint"],
        "source": record.meta["source"],
    }


def create_resource(
    root: Path,
    payload: Mapping[str, Any],
    *,
    created_by: str,
    proposed_by: str | None = None,
    import_batch: str | None = None,
    previous: ResourceRevision | None = None,
    lifecycle: str = "active",
) -> ResourceRevision:
    body = payload.get("body", "")
    if not isinstance(body, str):
        raise CanonicalError("RESOURCE_BODY_INVALID", "Resource body must be Markdown text")
    normalized = normalized_markdown(body)
    resource_id = str(previous.meta["resource_id"]) if previous else str(payload.get("resource_id") or uuid.uuid4())
    if not valid_uuid(resource_id):
        raise CanonicalError("RESOURCE_ID_INVALID", "Resource ID must be a UUID")
    revision_id = str(uuid.uuid4())
    source_input = payload.get("source")
    if not isinstance(source_input, Mapping):
        raise CanonicalError("RESOURCE_SOURCE_INVALID", "Resource source metadata is required")
    source = {
        "type": source_input.get("type"),
        "locator": safe_locator(source_input.get("locator")),
        "fingerprint": source_input.get("fingerprint"),
    }
    meta = {
        "schema": RESOURCE_SCHEMA,
        "schema_version": 1,
        "resource_id": resource_id,
        "revision_id": revision_id,
        "uri": resource_uri(resource_id),
        "resource_type": payload.get("resource_type"),
        "title": safe_title(payload.get("title")),
        "owner": str(payload.get("owner", "owner")).strip(),
        "authority_domain": str(payload.get("authority_domain", "personal")).strip(),
        "sensitivity": payload.get("sensitivity", "general"),
        "created_at": utc_now(),
        "source_at": payload.get("source_at"),
        "verified_at": payload.get("verified_at"),
        "freshness_at": payload.get("freshness_at"),
        "source": source,
        "created_by": created_by,
        "proposed_by": proposed_by or created_by,
        "review_state": "approved",
        "lifecycle": lifecycle,
        "supersedes_revision": previous.meta["revision_id"] if previous else None,
        "content_fingerprint": content_fingerprint(normalized),
        "attachment_manifest": payload.get("attachment_manifest"),
        "import_batch": import_batch,
    }
    path = resource_path(root, meta)
    write_resource(path, meta, normalized)
    record = parse_resource(path)
    errors = validate_resource(record)
    if errors:
        path.unlink(missing_ok=True)
        raise CanonicalError("RESOURCE_INVALID", "Generated resource failed validation", {"errors": errors})
    return record


def attachment_manifest_files(root: Path) -> list[Path]:
    return sorted((root / "brain" / "attachments" / "manifests").glob("*.json"))


def validate_attachment_manifest(root: Path, value: Any) -> list[str]:
    errors: list[str] = []
    required = {"schema", "manifest_id", "created_at", "created_by", "sensitivity", "encrypted", "files"}
    if not isinstance(value, dict) or set(value) != required:
        return ["attachment manifest fields are not exact"]
    if value.get("schema") != ATTACHMENT_SCHEMA or not valid_uuid(value.get("manifest_id")):
        errors.append("attachment manifest schema or ID is invalid")
    if not valid_timestamp(value.get("created_at")) or not valid_uuid(value.get("created_by")):
        errors.append("attachment provenance is invalid")
    if value.get("sensitivity") not in SENSITIVITIES or not isinstance(value.get("encrypted"), bool):
        errors.append("attachment sensitivity metadata is invalid")
    if value.get("sensitivity") == "sensitive":
        errors.append("sensitive synchronized attachments are unavailable pending security review")
    if contains_secret_like(value):
        errors.append("attachment manifest contains possible secret material")
    files = value.get("files")
    if not isinstance(files, list) or not files:
        errors.append("attachment manifest files must be a non-empty array")
        return errors
    total = 0
    seen = set()
    for item in files:
        if not isinstance(item, dict) or set(item) != {"name", "media_type", "size", "sha256", "object"}:
            errors.append("attachment file metadata fields are not exact")
            continue
        name = unicodedata.normalize("NFC", str(item.get("name", "")))
        if (
            not name
            or name in seen
            or CONTROL_PATTERN.search(name)
            or "/" in name
            or "\\" in name
            or name in {".", ".."}
        ):
            errors.append("attachment display name is invalid")
        seen.add(name)
        if not isinstance(item.get("media_type"), str) or CONTROL_PATTERN.search(item["media_type"]):
            errors.append("attachment media type is invalid")
        size = item.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or not 0 <= size <= MAX_ATTACHMENT_BYTES:
            errors.append("attachment size is invalid")
            continue
        total += size
        digest = str(item.get("sha256", ""))
        if not SHA256_PATTERN.fullmatch(digest):
            errors.append("attachment digest is invalid")
            continue
        hex_digest = digest.removeprefix("sha256:")
        expected = f"brain/attachments/objects/sha256/{hex_digest[:2]}/{hex_digest}"
        if item.get("object") != expected:
            errors.append("attachment object path is not content-addressed")
            continue
        object_path = root / expected
        try:
            state = os.lstat(object_path)
            if stat.S_ISLNK(state.st_mode) or not stat.S_ISREG(state.st_mode):
                raise OSError("unsafe object")
            content = object_path.read_bytes()
        except OSError:
            errors.append("attachment object is missing or unsafe")
            continue
        if len(content) != size or fingerprint_bytes(content) != f"sha256:{hex_digest}":
            errors.append("attachment object size or digest does not match")
    if total > MAX_ATTACHMENT_BYTES:
        errors.append("attachment manifest expanded size exceeds the limit")
    return errors


def create_attachment_manifest(
    root: Path,
    files: Iterable[Path],
    *,
    created_by: str,
    sensitivity: str,
    detect_secret: Any | None = None,
) -> tuple[dict[str, Any], list[Path]]:
    if sensitivity == "sensitive":
        raise CanonicalError(
            "SENSITIVE_SYNC_UNAVAILABLE",
            "Sensitive synchronized attachments require separate security review",
        )
    entries = []
    created_paths = []
    total = 0
    for source in files:
        try:
            state = os.lstat(source)
            if stat.S_ISLNK(state.st_mode) or not stat.S_ISREG(state.st_mode):
                raise OSError("unsafe source")
            content = source.read_bytes()
        except OSError as error:
            raise CanonicalError("ATTACHMENT_SOURCE_UNSAFE", "Attachment source is missing or unsafe") from error
        total += len(content)
        if detect_secret is not None and detect_secret(content.decode("utf-8", errors="ignore")):
            raise CanonicalError("SECRET_VALUE_REJECTED", "Attachment contains possible secret material")
        if total > MAX_ATTACHMENT_BYTES:
            raise CanonicalError("ATTACHMENT_LIMIT_EXCEEDED", "Attachment batch exceeds the size limit")
        digest = fingerprint_bytes(content)
        hex_digest = digest.removeprefix("sha256:")
        relative_object = Path("brain") / "attachments" / "objects" / "sha256" / hex_digest[:2] / hex_digest
        destination = root / relative_object
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.read_bytes() != content:
            raise CanonicalError("ATTACHMENT_DIGEST_COLLISION", "Attachment digest collision detected")
        if not destination.exists():
            descriptor, temporary_name = tempfile.mkstemp(prefix=".attachment-", dir=destination.parent)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary_name, destination)
            finally:
                Path(temporary_name).unlink(missing_ok=True)
        created_paths.append(destination)
        entries.append({
            "name": safe_title(source.name),
            "media_type": "application/octet-stream",
            "size": len(content),
            "sha256": digest,
            "object": str(relative_object),
        })
    manifest = {
        "schema": ATTACHMENT_SCHEMA,
        "manifest_id": str(uuid.uuid4()),
        "created_at": utc_now(),
        "created_by": created_by,
        "sensitivity": sensitivity,
        "encrypted": False,
        "files": entries,
    }
    path = root / "brain" / "attachments" / "manifests" / f"{manifest['manifest_id']}.json"
    atomic_json(path, manifest)
    errors = validate_attachment_manifest(root, manifest)
    if errors:
        path.unlink(missing_ok=True)
        raise CanonicalError("ATTACHMENT_MANIFEST_INVALID", "Generated attachment manifest is invalid", {"errors": errors})
    return manifest, [*created_paths, path]


def policy_files(root: Path) -> list[Path]:
    return sorted((root / "brain" / "policies").glob("*/*.json"))


def validate_policy(value: Any) -> list[str]:
    errors: list[str] = []
    required = {
        "schema",
        "policy_id",
        "revision_id",
        "agent_id",
        "effect",
        "capabilities",
        "collections",
        "sensitivity_ceiling",
        "platforms",
        "chat_types",
        "source_kinds",
        "owner_dm_only",
        "created_at",
        "created_by",
        "supersedes_revision",
        "revoked",
    }
    if not isinstance(value, dict) or set(value) != required:
        return ["policy fields are not exact"]
    for field in ("policy_id", "revision_id", "agent_id", "created_by"):
        if not valid_uuid(value.get(field)):
            errors.append(f"{field} must be a UUID")
    if value.get("effect") not in {"allow", "deny"}:
        errors.append("policy effect is invalid")
    capabilities = value.get("capabilities")
    if not isinstance(capabilities, list) or not set(capabilities) <= CAPABILITIES:
        errors.append("policy capabilities are invalid")
    for field in ("collections", "platforms", "chat_types", "source_kinds"):
        items = value.get(field)
        if not isinstance(items, list) or not all(
            isinstance(item, str) and item and not CONTROL_PATTERN.search(item) for item in items
        ):
            errors.append(f"policy {field} are invalid")
    if value.get("sensitivity_ceiling") not in SENSITIVITIES:
        errors.append("policy sensitivity ceiling is invalid")
    if not isinstance(value.get("owner_dm_only"), bool) or not isinstance(value.get("revoked"), bool):
        errors.append("policy booleans are invalid")
    if not valid_timestamp(value.get("created_at")):
        errors.append("policy created_at is invalid")
    supersedes = value.get("supersedes_revision")
    if supersedes is not None and not valid_uuid(supersedes):
        errors.append("policy supersedes revision is invalid")
    if contains_secret_like(value):
        errors.append("policy contains possible secret material")
    return errors


def load_policies(root: Path) -> list[dict[str, Any]]:
    result = []
    for path in policy_files(root):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CanonicalError("POLICY_INVALID", "Access policy is unreadable") from error
        errors = validate_policy(value)
        if errors:
            raise CanonicalError("POLICY_INVALID", "Access policy is invalid", {"errors": errors})
        result.append(value)
    return result


def current_policies(root: Path) -> list[dict[str, Any]]:
    policies = load_policies(root)
    superseded = {str(policy["supersedes_revision"]) for policy in policies if policy["supersedes_revision"]}
    return [
        policy
        for policy in policies
        if policy["revision_id"] not in superseded and not policy["revoked"]
    ]


def policy_path(root: Path, value: Mapping[str, Any]) -> Path:
    return root / "brain" / "policies" / str(value["agent_id"]) / f"{value['revision_id']}.json"


def create_policy(
    root: Path,
    payload: Mapping[str, Any],
    *,
    created_by: str,
    previous: Mapping[str, Any] | None = None,
    revoked: bool = False,
) -> tuple[dict[str, Any], Path]:
    agent_id = str(payload.get("agent_id") or (previous or {}).get("agent_id") or "")
    value = {
        "schema": POLICY_SCHEMA,
        "policy_id": str((previous or {}).get("policy_id") or payload.get("policy_id") or uuid.uuid4()),
        "revision_id": str(uuid.uuid4()),
        "agent_id": agent_id,
        "effect": payload.get("effect", "allow"),
        "capabilities": sorted(set(payload.get("capabilities", []))),
        "collections": sorted(set(payload.get("collections", []))),
        "sensitivity_ceiling": payload.get("sensitivity_ceiling", "general"),
        "platforms": sorted(set(payload.get("platforms", []))),
        "chat_types": sorted(set(payload.get("chat_types", []))),
        "source_kinds": sorted(set(payload.get("source_kinds", []))),
        "owner_dm_only": payload.get("owner_dm_only", True),
        "created_at": utc_now(),
        "created_by": created_by,
        "supersedes_revision": (previous or {}).get("revision_id"),
        "revoked": revoked,
    }
    errors = validate_policy(value)
    if errors:
        raise CanonicalError("POLICY_INVALID", "Generated access policy is invalid", {"errors": errors})
    path = policy_path(root, value)
    atomic_json(path, value)
    return value, path


def _policy_audit(root: Path, event: Mapping[str, Any]) -> None:
    path = root / ".megabrain" / "audit" / "policy.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    safe = {
        "at": utc_now(),
        "action": event.get("action"),
        "decision": event.get("decision"),
        "reason": event.get("reason"),
        "policy_revision": event.get("policy_revision"),
        "sensitivity": event.get("sensitivity"),
        "agent_digest": fingerprint_bytes(str(event.get("agent_id", "")).encode("utf-8")),
    }
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(descriptor, canonical_json(safe) + b"\n")
    finally:
        os.close(descriptor)


def _matches_collection(policy: Mapping[str, Any], meta: Mapping[str, Any]) -> bool:
    collections = set(policy.get("collections", []))
    if "*" in collections:
        return True
    tags = {str(tag) for tag in meta.get("tags", [])}
    subject = str(meta.get("subject", ""))
    resource_type = str(meta.get("resource_type", ""))
    return bool(collections & tags) or subject in collections or resource_type in collections


def authorize(
    root: Path,
    *,
    meta: Mapping[str, Any],
    trusted_context: Mapping[str, Any],
    capability: str,
) -> bool:
    required_context = {
        "agent_id",
        "source_kind",
        "platform",
        "chat_type",
        "owner_verified",
    }
    sensitivity = str(meta.get("sensitivity", "general"))
    agent_id = str(trusted_context.get("agent_id", ""))
    if not required_context <= set(trusted_context) or capability not in CAPABILITIES:
        _policy_audit(root, {"action": capability, "decision": "deny", "reason": "untrusted_context", "sensitivity": sensitivity, "agent_id": agent_id})
        return False
    matches = []
    for policy in current_policies(root):
        if policy["agent_id"] != agent_id or capability not in policy["capabilities"]:
            continue
        if policy["platforms"] and trusted_context["platform"] not in policy["platforms"]:
            continue
        if policy["chat_types"] and trusted_context["chat_type"] not in policy["chat_types"]:
            continue
        if policy["source_kinds"] and trusted_context["source_kind"] not in policy["source_kinds"]:
            continue
        if policy["owner_dm_only"] and not (
            trusted_context["owner_verified"] is True
            and trusted_context["source_kind"] == "gateway_user"
            and trusted_context["chat_type"] == "dm"
        ):
            continue
        if ACCESS_LEVEL[sensitivity] > ACCESS_LEVEL[policy["sensitivity_ceiling"]]:
            continue
        if not _matches_collection(policy, meta):
            continue
        matches.append(policy)
    denied = next((policy for policy in matches if policy["effect"] == "deny"), None)
    allowed = next((policy for policy in matches if policy["effect"] == "allow"), None)
    selected = denied or allowed
    decision = bool(allowed and not denied)
    _policy_audit(root, {
        "action": capability,
        "decision": "allow" if decision else "deny",
        "reason": "matched_policy" if selected else "default_deny",
        "policy_revision": selected.get("revision_id") if selected else None,
        "sensitivity": sensitivity,
        "agent_id": agent_id,
    })
    return decision


def authorize_memory_read(
    root: Path,
    meta: Mapping[str, Any],
    trusted_context: Mapping[str, Any],
) -> bool:
    return authorize(root, meta=meta, trusted_context=trusted_context, capability="read")


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(dict(value), stream, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
        os.chmod(path, 0o600)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def stage_path(root: Path, batch_id: str) -> Path:
    return root / ".megabrain" / "import-staging" / f"{batch_id}.json"


def coverage_summary(entries: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(entries)
    counts = Counter(str(row.get("status")) for row in rows)
    return {
        "total": len(rows),
        "by_status": dict(sorted(counts.items())),
        "unresolved": sum(
            status not in {"imported", "duplicate", "rejected", "intentionally-skipped", "acceptance-tested"}
            for status in counts.elements()
        ),
    }


def validate_coverage(entries: Any) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        raise CanonicalError("COVERAGE_INVALID", "Coverage must be an array")
    normalized = []
    seen = set()
    confusable_seen = set()
    for raw in entries:
        if not isinstance(raw, Mapping):
            raise CanonicalError("COVERAGE_INVALID", "Coverage entries must be objects")
        locator = safe_locator(raw.get("locator"))
        status = raw.get("status")
        fingerprint = raw.get("fingerprint")
        if status not in COVERAGE_STATUSES:
            raise CanonicalError("COVERAGE_INVALID", "Coverage status is invalid")
        if fingerprint is not None and not SHA256_PATTERN.fullmatch(str(fingerprint)):
            raise CanonicalError("COVERAGE_INVALID", "Coverage fingerprint is invalid")
        skeleton = unicodedata.normalize("NFKC", locator).casefold()
        if locator in seen or skeleton in confusable_seen:
            raise CanonicalError("COVERAGE_INVALID", "Coverage locators must be unique after Unicode normalization")
        seen.add(locator)
        confusable_seen.add(skeleton)
        normalized.append({
            "locator": locator,
            "status": status,
            "fingerprint": fingerprint,
            "reason": str(raw.get("reason", ""))[:200],
        })
    return normalized


def _candidate_fingerprint(candidate: Mapping[str, Any]) -> str:
    clean = {key: value for key, value in candidate.items() if key != "candidate_fingerprint"}
    return fingerprint_bytes(canonical_json(clean))


def stage_import(root: Path, payload: Mapping[str, Any], *, detect_secret: Any) -> dict[str, Any]:
    if detect_secret(payload):
        raise CanonicalError("SECRET_VALUE_REJECTED", "Import package contains possible secret material")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= MAX_IMPORT_CANDIDATES:
        raise CanonicalError("IMPORT_CANDIDATES_INVALID", "Import batches require 1 to 10 candidates")
    coverage = validate_coverage(payload.get("coverage"))
    normalized_candidates = []
    seen_ids = set()
    seen_fingerprints = set()
    for raw in candidates:
        if not isinstance(raw, Mapping):
            raise CanonicalError("IMPORT_CANDIDATES_INVALID", "Import candidates must be objects")
        candidate = dict(raw)
        candidate_id = str(candidate.get("candidate_id") or uuid.uuid4())
        if not valid_uuid(candidate_id) or candidate_id in seen_ids:
            raise CanonicalError("IMPORT_CANDIDATES_INVALID", "Candidate IDs must be unique UUIDs")
        seen_ids.add(candidate_id)
        kind = candidate.get("kind")
        if kind not in {"memory", "resource"}:
            raise CanonicalError("IMPORT_CANDIDATES_INVALID", "Candidate kind must be memory or resource")
        data = candidate.get("data")
        if not isinstance(data, Mapping):
            raise CanonicalError("IMPORT_CANDIDATES_INVALID", "Candidate data must be an object")
        if detect_secret(data):
            raise CanonicalError("SECRET_VALUE_REJECTED", "Import candidate contains possible secret material")
        if kind == "resource" and len(str(data.get("body", "")).encode("utf-8")) > MAX_RESOURCE_BYTES:
            raise CanonicalError("IMPORT_LIMIT_EXCEEDED", "Resource candidate exceeds the size limit")
        normalized = {
            "candidate_id": candidate_id,
            "kind": kind,
            "data": dict(data),
            "source_locator": safe_locator(candidate.get("source_locator")),
            "source_fingerprint": candidate.get("source_fingerprint"),
            "instruction_like": any(
                pattern.search(str(data.get("body", data.get("summary", ""))))
                for pattern in INSTRUCTION_PATTERNS
            ),
        }
        if not SHA256_PATTERN.fullmatch(str(normalized["source_fingerprint"])):
            raise CanonicalError("IMPORT_CANDIDATES_INVALID", "Candidate source fingerprint is invalid")
        normalized["candidate_fingerprint"] = _candidate_fingerprint(normalized)
        if normalized["candidate_fingerprint"] in seen_fingerprints:
            raise CanonicalError("IMPORT_CANDIDATES_INVALID", "Candidate fingerprints must be unique")
        seen_fingerprints.add(normalized["candidate_fingerprint"])
        normalized_candidates.append(normalized)
    package = {
        "schema": CANDIDATE_SCHEMA,
        "batch_id": str(uuid.uuid4()),
        "created_at": utc_now(),
        "source": {
            "type": str(payload.get("source_type", "filesystem")),
            "locator": safe_locator(payload.get("source_locator")),
        },
        "coverage": coverage,
        "candidates": normalized_candidates,
    }
    package["batch_fingerprint"] = fingerprint_bytes(canonical_json(package))
    if len(canonical_json(package)) > MAX_IMPORT_BYTES:
        raise CanonicalError("IMPORT_LIMIT_EXCEEDED", "Import package exceeds the expanded-size limit")
    path = stage_path(root, package["batch_id"])
    atomic_json(path, package)
    return {
        "ok": True,
        "status": "staged",
        "batch_id": package["batch_id"],
        "batch_fingerprint": package["batch_fingerprint"],
        "candidates": len(normalized_candidates),
        "instruction_like": sum(bool(item["instruction_like"]) for item in normalized_candidates),
        "coverage": coverage_summary(coverage),
        "path": str(path),
    }


def load_stage(root: Path, batch_id: str) -> dict[str, Any]:
    if not valid_uuid(batch_id):
        raise CanonicalError("IMPORT_BATCH_INVALID", "Import batch ID must be a UUID")
    path = stage_path(root, batch_id)
    try:
        state = os.lstat(path)
        if stat.S_ISLNK(state.st_mode) or not stat.S_ISREG(state.st_mode):
            raise CanonicalError("IMPORT_STAGE_UNSAFE", "Import stage file is unsafe")
        package = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CanonicalError("IMPORT_BATCH_NOT_FOUND", "Import batch was not found") from error
    expected = package.get("batch_fingerprint") if isinstance(package, dict) else None
    clean = dict(package) if isinstance(package, dict) else {}
    clean.pop("batch_fingerprint", None)
    if (
        package.get("schema") != CANDIDATE_SCHEMA
        or expected != fingerprint_bytes(canonical_json(clean))
        or package.get("batch_id") != batch_id
    ):
        raise CanonicalError("IMPORT_STAGE_CHANGED", "Staged import changed after review")
    return package


def deterministic_export(records: Iterable[ResourceRevision]) -> str:
    sections = []
    for record in sorted(records, key=lambda item: (item.meta["uri"], item.meta["revision_id"])):
        meta = resource_metadata(record)
        header = json.dumps(meta, ensure_ascii=True, sort_keys=True, indent=2)
        sections.append(
            f"<!-- megabrain-export\n{header}\n-->\n\n# {record.meta['title']}\n\n{record.body.strip()}\n"
        )
    return "\n".join(sections)


def parse_deterministic_export(value: str) -> list[ResourceRevision]:
    pattern = re.compile(
        r"<!-- megabrain-export\n(?P<meta>.*?)\n-->\n\n# (?P<title>[^\n]+)\n\n(?P<body>.*?)(?=\n<!-- megabrain-export\n|\Z)",
        re.DOTALL,
    )
    records = []
    position = 0
    for match in pattern.finditer(value):
        if value[position:match.start()].strip():
            raise CanonicalError("EXPORT_INVALID", "Deterministic export contains unexpected data")
        try:
            meta = json.loads(match.group("meta"))
        except json.JSONDecodeError as error:
            raise CanonicalError("EXPORT_INVALID", "Deterministic export metadata is invalid") from error
        if not isinstance(meta, dict) or meta.get("title") != match.group("title"):
            raise CanonicalError("EXPORT_INVALID", "Deterministic export title does not match metadata")
        body = normalized_markdown(match.group("body"))
        if meta.get("content_fingerprint") != content_fingerprint(body):
            raise CanonicalError("EXPORT_INVALID", "Deterministic export fingerprint does not match content")
        records.append(ResourceRevision(path=Path(str(meta["revision_id"])), meta=meta, body=body))
        position = match.end()
    if value[position:].strip() or not records:
        raise CanonicalError("EXPORT_INVALID", "Deterministic export is empty or malformed")
    return records


def drift_report(root: Path, memories: Iterable[Any]) -> dict[str, Any]:
    legacy = ("obsidian://", "hermes://", "super-brain://", "pierre-memory://")
    pointers = []
    for record in memories:
        source = record.meta.get("source", {})
        locator = str(source.get("locator", "")) if isinstance(source, Mapping) else ""
        if locator.startswith(legacy):
            pointers.append({"kind": "memory", "id": record.meta.get("id"), "locator": locator})
    for record in load_resources(root):
        locator = str(record.meta.get("source", {}).get("locator", ""))
        if locator.startswith(legacy):
            pointers.append({"kind": "resource", "id": record.meta.get("resource_id"), "locator": locator})
    return {"ok": True, "obsolete_pointer_count": len(pointers), "obsolete_pointers": pointers}


def cache_projection(memories: Iterable[Any], *, limit: int = 3) -> str:
    selected = [
        record
        for record in memories
        if record.meta.get("importance") == "always" and record.meta.get("sensitivity") == "general"
    ]
    selected.sort(key=lambda item: (str(item.meta.get("subject")), str(item.meta.get("id"))))
    lines = ["# MegaBrain derived cache", "", "Generated projection. Do not edit or write back.", ""]
    for record in selected[:limit]:
        summary = " ".join(line.strip() for line in record.body.splitlines() if line.strip() and not line.startswith("#"))
        lines.extend((f"- `{record.meta['id']}` {summary}",))
    return "\n".join(lines).rstrip() + "\n"


def update_intake_state(
    root: Path,
    inventory: Mapping[str, str],
    *,
    state_root: Path,
) -> dict[str, Any]:
    if root.resolve() == state_root.resolve() or root.resolve() in state_root.resolve().parents:
        raise CanonicalError("INTAKE_STATE_INVALID", "Watcher state must remain outside the repository")
    for locator, fingerprint in inventory.items():
        safe_locator(locator)
        if not SHA256_PATTERN.fullmatch(str(fingerprint)):
            raise CanonicalError("INTAKE_STATE_INVALID", "Inventory fingerprints must be SHA-256")
    state_path = state_root / "intake-state.json"
    try:
        previous = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        previous = {"inventory": {}}
    previous_inventory = previous.get("inventory", {}) if isinstance(previous, dict) else {}
    changed = sorted(
        locator for locator, fingerprint in inventory.items() if previous_inventory.get(locator) != fingerprint
    )
    removed = sorted(set(previous_inventory) - set(inventory))
    atomic_json(state_path, {"schema": "megabrain.intake-state.v1", "inventory": dict(sorted(inventory.items()))})
    return {
        "ok": True,
        "review_required": bool(changed or removed),
        "changed": changed[:100],
        "removed": removed[:100],
        "heartbeat": "healthy",
        "state_path": str(state_path),
    }
