#!/usr/bin/env python3
"""Owner-local controls for canonical resources, policies, imports, and migration."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import canonical
import megabrain


def require_owner_local(*, trusted_local: bool = False) -> None:
    if trusted_local:
        return
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise canonical.CanonicalError(
            "OWNER_LOCAL_CONTROL_REQUIRED",
            "Open this command in an owner-local interactive terminal",
        )
    confirmation = input("Type APPROVE LOCAL CANONICAL CHANGE: ").strip()
    if confirmation != "APPROVE LOCAL CANONICAL CHANGE":
        raise canonical.CanonicalError("OWNER_APPROVAL_DENIED", "Owner-local approval was not confirmed")


def prepare_write(
    root: Path,
    *,
    require_protocol: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    megabrain.require_compatible_runtime(root, writing=True)
    if require_protocol:
        megabrain.require_canonical_protocol(root)
    identity = megabrain.load_identity(root)
    sync = megabrain.sync_repo(root)
    megabrain.require_clean_or_offline(sync)
    return identity, sync


def _remove_created(paths: list[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def approve_import(
    root: Path,
    payload: Mapping[str, Any],
    *,
    trusted_local: bool = False,
) -> dict[str, Any]:
    require_owner_local(trusted_local=trusted_local)
    batch_id = str(payload.get("batch_id", ""))
    reviewed_fingerprint = str(payload.get("batch_fingerprint", ""))
    decisions = payload.get("decisions")
    current_sources = payload.get("current_source_fingerprints")
    if not isinstance(decisions, Mapping) or not isinstance(current_sources, Mapping):
        raise canonical.CanonicalError(
            "IMPORT_APPROVAL_INVALID",
            "Approval requires exact candidate decisions and current source fingerprints",
        )
    lock_path = root / ".megabrain" / "import-approval.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with lock_path.open("a+", encoding="utf-8") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        identity, sync = prepare_write(root)
        package = canonical.load_stage(root, batch_id)
        if package["batch_fingerprint"] != reviewed_fingerprint:
            raise canonical.CanonicalError(
                "IMPORT_APPROVAL_MISMATCH",
                "Approval fingerprint does not match the reviewed batch",
            )
        for candidate in package["candidates"]:
            locator = candidate["source_locator"]
            if current_sources.get(locator) != candidate["source_fingerprint"]:
                raise canonical.CanonicalError(
                    "IMPORT_SOURCE_CHANGED",
                    "A source changed after review; restage the batch",
                )
        expected_ids = {candidate["candidate_id"] for candidate in package["candidates"]}
        if set(decisions) != expected_ids or not set(decisions.values()) <= {"approve", "reject"}:
            raise canonical.CanonicalError(
                "IMPORT_APPROVAL_INVALID",
                "Every candidate requires an exact approve or reject decision",
            )
        for record in megabrain.load_records(megabrain.import_files(root)):
            if record.meta.get("id") == batch_id:
                return {
                    "ok": True,
                    "status": "already_imported",
                    "import_id": batch_id,
                    "sync": sync,
                }
        created_memories = []
        created_resources = []
        created_paths: list[Path] = []
        duplicate_ids = []
        conflicts = []
        rejected = Counter()
        candidate_outcomes: dict[str, str] = {}
        existing_resources = canonical.load_resources(root)
        existing_fingerprints = {
            str(record.meta.get("content_fingerprint")): record for record in existing_resources
        }
        shared_source = {
            "type": "import",
            "locator": package["source"]["locator"],
            "hash": package["batch_fingerprint"],
            "import_batch": batch_id,
        }
        try:
            for candidate in package["candidates"]:
                if decisions[candidate["candidate_id"]] == "reject":
                    rejected["owner_rejected"] += 1
                    candidate_outcomes[candidate["candidate_id"]] = "rejected"
                    continue
                data = dict(candidate["data"])
                if candidate["kind"] == "memory":
                    if candidate["instruction_like"]:
                        rejected["instruction_memory_rejected"] += 1
                        candidate_outcomes[candidate["candidate_id"]] = "rejected"
                        continue
                    data.setdefault("confidence", "unconfirmed")
                    record, duplicate, conflict_ids = megabrain.create_memory_file(
                        root,
                        identity,
                        data,
                        source=shared_source,
                        importing=True,
                    )
                    if duplicate:
                        duplicate_ids.append(str(duplicate.meta["id"]))
                        candidate_outcomes[candidate["candidate_id"]] = "duplicate"
                        continue
                    assert record is not None
                    created_memories.append(record)
                    created_paths.append(record.path)
                    if conflict_ids:
                        conflicts.append({"subject": record.meta["subject"], "memory_ids": conflict_ids})
                        candidate_outcomes[candidate["candidate_id"]] = "conflict"
                    else:
                        candidate_outcomes[candidate["candidate_id"]] = "imported"
                    continue
                data["source"] = {
                    "type": "import",
                    "locator": candidate["source_locator"],
                    "fingerprint": candidate["source_fingerprint"],
                }
                candidate_fingerprint = canonical.content_fingerprint(str(data.get("body", "")))
                duplicate = existing_fingerprints.get(candidate_fingerprint)
                if duplicate:
                    duplicate_ids.append(str(duplicate.meta["resource_id"]))
                    candidate_outcomes[candidate["candidate_id"]] = "duplicate"
                    continue
                record = canonical.create_resource(
                    root,
                    data,
                    created_by=identity["id"],
                    proposed_by=identity["id"],
                    import_batch=batch_id,
                )
                created_resources.append(record)
                created_paths.append(record.path)
                existing_fingerprints[record.meta["content_fingerprint"]] = record
                candidate_outcomes[candidate["candidate_id"]] = "imported"
            coverage = []
            outcomes_by_locator: dict[str, set[str]] = {}
            for candidate in package["candidates"]:
                outcomes_by_locator.setdefault(candidate["source_locator"], set()).add(
                    candidate_outcomes[candidate["candidate_id"]]
                )
            for entry in package["coverage"]:
                updated = dict(entry)
                outcomes = outcomes_by_locator.get(entry["locator"], set())
                for status in ("conflict", "imported", "duplicate", "rejected"):
                    if status in outcomes:
                        updated["status"] = status
                        break
                coverage.append(updated)
            counts = {
                "scanned": len(package["candidates"]),
                "created": len(created_memories) + len(created_resources),
                "duplicates": len(duplicate_ids),
                "conflicts": len(conflicts),
                "rejected": sum(rejected.values()),
            }
            manifest_meta = {
                "schema": megabrain.IMPORT_SCHEMA,
                "id": batch_id,
                "created_at": megabrain.utc_now(),
                "created_by": identity["id"],
                "source": {
                    "type": package["source"]["type"],
                    "locator": package["source"]["locator"],
                    "hash": package["batch_fingerprint"],
                },
                "counts": counts,
                "coverage": coverage,
                "created_memory_ids": [record.meta["id"] for record in created_memories],
                "created_resource_ids": [record.meta["resource_id"] for record in created_resources],
                "duplicate_ids": duplicate_ids,
                "conflicts": conflicts,
                "rejected_by_code": dict(sorted(rejected.items())),
                "reviewed_fingerprint": reviewed_fingerprint,
            }
            manifest = root / "brain" / "imports" / f"{batch_id}.md"
            megabrain.write_record(
                manifest,
                manifest_meta,
                "# Canonical Import Batch\n\nFingerprint-bound owner approval; source content remains inert data.",
            )
            created_paths.append(manifest)
            errors = megabrain.validate_import(megabrain.parse_record(manifest))
            validation = megabrain.command_validate(root)
            if errors or not validation["ok"]:
                raise canonical.CanonicalError(
                    "IMPORT_VALIDATION_FAILED",
                    "Approved import would make the repository invalid",
                    {"errors": [*errors, *[item["message"] for item in validation["errors"]]]},
                )
            commit = megabrain.commit_paths(
                root,
                created_paths,
                f"canonical({identity['harness']}): import {counts['created']} approved records",
            )
        except Exception:
            _remove_created(created_paths)
            raise
    return {
        "ok": True,
        "status": "imported",
        "import_id": batch_id,
        "counts": counts,
        "created_memory_ids": manifest_meta["created_memory_ids"],
        "created_resource_ids": manifest_meta["created_resource_ids"],
        "duplicate_ids": duplicate_ids,
        "conflicts": conflicts,
        "notice": f"MegaBrain: imported {counts['created']} approved canonical records.",
        **commit,
    }


def create_or_revise_resource(
    root: Path,
    payload: Mapping[str, Any],
    *,
    reference: str | None = None,
    retire: bool = False,
    trusted_local: bool = False,
) -> dict[str, Any]:
    require_owner_local(trusted_local=trusted_local)
    identity, _ = prepare_write(root)
    previous = canonical.find_resource(root, reference)[0] if reference else None
    selected = dict(payload)
    if megabrain.detect_secret(selected):
        raise canonical.CanonicalError("SECRET_VALUE_REJECTED", "Resource contains possible secret material")
    if previous:
        for field in ("resource_type", "owner", "authority_domain", "sensitivity"):
            selected.setdefault(field, previous.meta[field])
        selected.setdefault("title", previous.meta["title"])
        selected.setdefault("body", "" if retire else previous.body)
    record = canonical.create_resource(
        root,
        selected,
        created_by=identity["id"],
        previous=previous,
        lifecycle="retired" if retire else "active",
    )
    validation = megabrain.command_validate(root)
    if not validation["ok"]:
        record.path.unlink(missing_ok=True)
        raise canonical.CanonicalError("RESOURCE_VALIDATION_FAILED", "Resource revision failed repository validation")
    commit = megabrain.commit_paths(
        root,
        [record.path],
        f"canonical({identity['harness']}): {'retire' if retire else 'revise' if previous else 'create'} {record.meta['resource_type']}",
    )
    return {"ok": True, "resource": canonical.resource_metadata(record), **commit}


def set_policy(
    root: Path,
    payload: Mapping[str, Any],
    *,
    revoke: bool = False,
    trusted_local: bool = False,
) -> dict[str, Any]:
    require_owner_local(trusted_local=trusted_local)
    identity, _ = prepare_write(root)
    previous = None
    policy_id = payload.get("policy_id")
    if policy_id:
        previous = next(
            (policy for policy in canonical.current_policies(root) if policy["policy_id"] == policy_id),
            None,
        )
        if previous is None:
            raise canonical.CanonicalError("POLICY_NOT_FOUND", "Current access policy was not found")
    value, path = canonical.create_policy(
        root,
        payload,
        created_by=identity["id"],
        previous=previous,
        revoked=revoke,
    )
    validation = megabrain.command_validate(root)
    if not validation["ok"]:
        path.unlink(missing_ok=True)
        raise canonical.CanonicalError("POLICY_VALIDATION_FAILED", "Policy revision failed repository validation")
    commit = megabrain.commit_paths(
        root,
        [path],
        f"policy({identity['harness']}): {'revoke' if revoke else 'set'} scoped access",
    )
    return {
        "ok": True,
        "policy_id": value["policy_id"],
        "revision_id": value["revision_id"],
        "revoked": value["revoked"],
        **commit,
    }


def add_attachment(
    root: Path,
    sources: list[str],
    sensitivity: str,
    *,
    trusted_local: bool = False,
) -> dict[str, Any]:
    require_owner_local(trusted_local=trusted_local)
    identity, _ = prepare_write(root)
    manifest, paths = canonical.create_attachment_manifest(
        root,
        [Path(source).expanduser().resolve() for source in sources],
        created_by=identity["id"],
        sensitivity=sensitivity,
        detect_secret=megabrain.detect_secret,
    )
    validation = megabrain.command_validate(root)
    if not validation["ok"]:
        _remove_created(paths)
        raise canonical.CanonicalError("ATTACHMENT_VALIDATION_FAILED", "Attachment failed repository validation")
    commit = megabrain.commit_paths(
        root,
        paths,
        f"canonical({identity['harness']}): add content-addressed attachment",
    )
    return {"ok": True, "manifest_id": manifest["manifest_id"], "files": len(manifest["files"]), **commit}


def migrate_v1(root: Path, *, trusted_local: bool = False) -> dict[str, Any]:
    require_owner_local(trusted_local=trusted_local)
    identity, _ = prepare_write(root, require_protocol=False)
    manifest_path = root / "megabrain.json"
    original = json.loads(manifest_path.read_text(encoding="utf-8"))
    if original.get("protocol_version") == 2:
        return {"ok": True, "status": "already_migrated"}
    if original.get("protocol_version") != 1:
        raise canonical.CanonicalError("MIGRATION_UNSUPPORTED", "Only protocol 1 can migrate to protocol 2")
    paths = [manifest_path]
    directories = [
        *(root / "brain" / "resources" / directory for directory in canonical.RESOURCE_TYPES.values()),
        root / "brain" / "attachments" / "manifests",
        root / "brain" / "attachments" / "objects" / "sha256",
        root / "brain" / "policies",
    ]
    created = []
    try:
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            marker = directory / ".gitkeep"
            if not marker.exists():
                marker.write_text("", encoding="utf-8")
                created.append(marker)
                paths.append(marker)
        upgraded = dict(original)
        upgraded["protocol_version"] = 2
        upgraded["minimum_runtime"] = "2.0.0"
        manifest_path.write_text(json.dumps(upgraded, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        validation = megabrain.command_validate(root)
        if not validation["ok"]:
            raise canonical.CanonicalError("MIGRATION_VALIDATION_FAILED", "Protocol migration failed validation")
        commit = megabrain.commit_paths(root, paths, f"canonical({identity['harness']}): migrate protocol 1 to 2")
    except Exception:
        manifest_path.write_text(json.dumps(original, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _remove_created(created)
        raise
    return {"ok": True, "status": "migrated", "from_protocol": 1, "to_protocol": 2, **commit}


def rollback_head(root: Path, *, trusted_local: bool = False) -> dict[str, Any]:
    require_owner_local(trusted_local=trusted_local)
    prepare_write(root)
    subject = megabrain.run(["git", "log", "-1", "--format=%s"], root)
    if subject.returncode != 0 or not subject.stdout.startswith(("canonical(", "policy(")):
        raise canonical.CanonicalError(
            "ROLLBACK_BOUNDARY_INVALID",
            "Only the current canonical or policy commit can be rolled back automatically",
        )
    reverted = megabrain.run(["git", "revert", "--no-edit", "HEAD"], root)
    if reverted.returncode != 0:
        megabrain.run(["git", "revert", "--abort"], root)
        raise canonical.CanonicalError("ROLLBACK_FAILED", "Canonical rollback failed")
    validation = megabrain.command_validate(root)
    if not validation["ok"]:
        raise canonical.CanonicalError("ROLLBACK_VALIDATION_FAILED", "Rollback left an invalid repository")
    pushed, reason = megabrain.push_with_retry(root)
    return {
        "ok": True,
        "rolled_back": True,
        "pushed": pushed,
        "pending_sync": not pushed,
        "reason": reason,
    }


def read_payload() -> dict[str, Any]:
    try:
        value = json.load(sys.stdin)
    except json.JSONDecodeError as error:
        raise canonical.CanonicalError("INVALID_JSON", "Input must be valid JSON") from error
    if not isinstance(value, dict):
        raise canonical.CanonicalError("INVALID_INPUT", "Input must be an object")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="canonical-local")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("approve-import", "resource-create", "policy-set"):
        commands.add_parser(name)
    revise = commands.add_parser("resource-revise")
    revise.add_argument("reference")
    retire = commands.add_parser("resource-retire")
    retire.add_argument("reference")
    revoke = commands.add_parser("policy-revoke")
    revoke.add_argument("policy_id")
    attachment = commands.add_parser("attachment-add")
    attachment.add_argument("sources", nargs="+")
    attachment.add_argument("--sensitivity", choices=sorted(canonical.SENSITIVITIES), default="general")
    commands.add_parser("migrate-v1")
    commands.add_parser("rollback-head")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        root = megabrain.repo_root()
        if args.command == "approve-import":
            result = approve_import(root, read_payload())
        elif args.command == "resource-create":
            result = create_or_revise_resource(root, read_payload())
        elif args.command == "resource-revise":
            result = create_or_revise_resource(root, read_payload(), reference=args.reference)
        elif args.command == "resource-retire":
            result = create_or_revise_resource(root, read_payload(), reference=args.reference, retire=True)
        elif args.command == "policy-set":
            result = set_policy(root, read_payload())
        elif args.command == "policy-revoke":
            result = set_policy(root, {"policy_id": args.policy_id}, revoke=True)
        elif args.command == "attachment-add":
            result = add_attachment(root, args.sources, args.sensitivity)
        elif args.command == "migrate-v1":
            result = migrate_v1(root)
        elif args.command == "rollback-head":
            result = rollback_head(root)
        else:
            raise canonical.CanonicalError("COMMAND_UNSUPPORTED", "Unsupported owner-local command")
        megabrain.emit(result)
        return 0
    except (canonical.CanonicalError, megabrain.BrainError) as error:
        megabrain.emit(
            {"ok": False, "error": {"code": error.code, "message": error.message, "details": error.details}},
            stream=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
