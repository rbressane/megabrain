"""Disposable, content-addressed parsing for committed Git records.

No working-tree reads. Unchanged blobs reuse parsed source rows; graph resolution
and derived postings are rebuilt atomically. Indexes never authorize access.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any, Callable

import operations

MAX_BATCH_BYTES = 128 * 1024 * 1024


def tree_id(root: Path, commit: str, subtree: str) -> str:
    result = operations.run(["git", "rev-parse", "--verify", f"{commit}:{subtree}"], root)
    return result.stdout.strip() if result.returncode == 0 else "absent"


def read_records(root: Path, commit: str, subtree: str, index: Path, schema: str,
                 parse: Callable, factory: Callable) -> tuple[list[Any], list[tuple]]:
    cached = {}
    connection = None
    try:
        if index.is_file() and not index.is_symlink():
            connection = sqlite3.connect(f"{index.as_uri()}?mode=ro", uri=True)
            metadata = dict(connection.execute("SELECT key,value FROM metadata"))
            if metadata.get("schema") == schema:
                cached = {row[0]: row[1:] for row in connection.execute("SELECT path,oid,meta_json,body FROM sources")}
    except (OSError, sqlite3.DatabaseError):
        cached = {}
    finally:
        if connection is not None:
            connection.close()
    result = operations.run(["git", "ls-tree", "-rlz", commit, "--", subtree], root, text=False)
    if result.returncode:
        raise operations.OperationError("INDEX_SOURCE_UNAVAILABLE", "Committed index sources could not be read.")
    entries = []
    missing = []
    total = 0
    for entry in result.stdout.split(b"\0"):
        if not entry:
            continue
        header, raw_path = entry.split(b"\t", 1)
        mode, kind, oid, size = header.split()
        path = raw_path.decode("utf-8")
        if mode != b"100644" or kind != b"blob" or not path.startswith(subtree + "/"):
            raise operations.OperationError("INDEX_SOURCE_UNSAFE", "A committed index source is unsafe.")
        if not path.endswith(".md"):
            continue
        if int(size) > operations.MAX_BLOB_BYTES:
            raise operations.OperationError("INDEX_SOURCE_UNSAFE", "A committed record exceeds safe limits.")
        oid = oid.decode("ascii")
        entries.append((path, oid))
        if path not in cached or cached[path][0] != oid:
            missing.append(oid)
            total += int(size)
    if total > MAX_BATCH_BYTES:
        raise operations.OperationError("INDEX_BATCH_TOO_LARGE", "Index sources exceed the bounded batch budget.")
    blobs = {}
    if missing:
        batch = operations.run(["git", "cat-file", "--batch"], root, text=False,
                               input=("\n".join(missing) + "\n").encode("ascii"))
        if batch.returncode:
            raise operations.OperationError("INDEX_SOURCE_UNAVAILABLE", "Committed objects could not be read.")
        offset = 0
        for expected in missing:
            end = batch.stdout.index(b"\n", offset)
            oid, kind, size = batch.stdout[offset:end].split()
            size = int(size)
            offset = end + 1
            if oid.decode("ascii") != expected or kind != b"blob" or offset + size >= len(batch.stdout):
                raise operations.OperationError("INDEX_SOURCE_INVALID", "A committed object response is invalid.")
            blobs[expected] = batch.stdout[offset:offset + size].decode("utf-8")
            offset += size + 1
    records, sources = [], []
    for path, oid in entries:
        previous = cached.get(path)
        if previous and previous[0] == oid:
            meta_json, body = previous[1:]
            record = factory(path=root / path, meta=json.loads(meta_json), body=body)
        else:
            record = parse(root / path, blobs[oid])
            meta_json = json.dumps(record.meta, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            body = record.body
        records.append(record)
        sources.append((path, oid, meta_json, body))
    return records, sources


def store_sources(connection: sqlite3.Connection, rows: list[tuple]) -> None:
    connection.execute("CREATE TABLE sources (path TEXT PRIMARY KEY, oid TEXT NOT NULL, meta_json TEXT NOT NULL, body TEXT NOT NULL)")
    connection.executemany("INSERT INTO sources VALUES (?, ?, ?, ?)", rows)
