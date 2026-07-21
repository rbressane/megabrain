#!/usr/bin/env python3
"""First-class consumer command for MegaBrain runtime operations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from bootstrap import (
    BootstrapError,
    OFFICIAL_DISTRIBUTION,
    load_config,
    repository_glance,
    update_runtime,
)


UPDATE_SCHEMA = "megabrain.update.v1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="megabrain",
        description="Manage the installed MegaBrain runtime and prepare privacy-safe product feedback.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    update = subparsers.add_parser("update", help="check or install stable MegaBrain releases")
    update.add_argument("--check", action="store_true", help="check without changing the active runtime")
    update.add_argument("--version", help="activate a specific compatible stable version")
    update.add_argument("--json", action="store_true", dest="json_output", help="emit stable machine-readable JSON")
    update.add_argument(
        "--approve-major",
        action="store_true",
        help="approve a major or protocol-version transition after reviewing it",
    )
    update.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
    return parser


def update_report(args: argparse.Namespace) -> dict[str, Any]:
    result = update_runtime(
        argparse.Namespace(
            home=args.home,
            automatic=False,
            check=args.check,
            version=args.version,
            approve_major=args.approve_major,
        )
    )
    active = str(result.get("current_version", ""))
    previous = str(result.get("previous_version") or active)
    latest_stable = str(result.get("latest_stable_version") or result.get("latest_version") or active)
    config = load_config(args.home.expanduser().resolve(), required=True)
    runtime = config.get("runtime") if isinstance(config.get("runtime"), dict) else {}
    remote = str(runtime.get("source") or OFFICIAL_DISTRIBUTION)
    glance = repository_glance(remote, previous, active, latest_stable)
    return {
        "schema": UPDATE_SCHEMA,
        "ok": bool(result.get("ok")),
        "operation": "check" if args.check else "update",
        "checked": bool(result.get("checked")),
        "updated": bool(result.get("updated")),
        "approval_required": bool(result.get("approval_required")),
        "approval_reason": result.get("approval_reason"),
        "previous_version": previous,
        "active_version": active,
        "target_version": result.get("latest_version") or active,
        "latest_stable_version": latest_stable,
        "update_available": bool(result.get("update_available")),
        "stale": bool(result.get("stale")),
        "repository": glance,
    }


def format_distance(label: str, distance: dict[str, Any], suffix: str) -> str | None:
    if not distance.get("available"):
        return None
    return (
        f"{label}: {distance['releases']} release(s), {distance['commits']} commit(s), "
        f"{distance['merged_prs']} merged PR(s) {suffix}."
    )


def format_update(report: dict[str, Any]) -> str:
    previous = report["previous_version"]
    active = report["active_version"]
    target = report["target_version"]
    lines: list[str] = []
    if report["approval_required"]:
        reason = "major version" if report["approval_reason"] == "major_version" else "protocol version"
        lines.append(f"MegaBrain v{target} requires explicit approval for a {reason} transition.")
        lines.append("Review the release, then rerun with --approve-major.")
    elif report["updated"]:
        verb = "rolled back" if tuple(map(int, active.split("."))) < tuple(map(int, previous.split("."))) else "updated"
        lines.append(f"MegaBrain {verb} v{previous} → v{active}.")
        included = format_distance("Included", report["repository"]["included"], "crossed")
        if included:
            lines.append(included)
        highlights = report["repository"]["included"].get("highlights", [])
        if highlights:
            lines.append("Highlights:")
            for item in highlights:
                prefix = f"#{item['number']} " if item.get("number") else ""
                lines.append(f"- {prefix}{item['title']}")
    elif report["operation"] == "check" and report["update_available"]:
        lines.append(f"MegaBrain v{active} can update to v{target}.")
    else:
        lines.append(f"MegaBrain v{active} is current.")

    stable = format_distance("Stable gap", report["repository"]["stable_gap"], "behind")
    if stable:
        lines.append(stable)
    development = report["repository"]["development"]
    if development.get("available"):
        lines.append(
            f"Development: main is {development['commits_ahead']} commit(s) ahead of the latest stable release."
        )
    open_work = report["repository"]["open_work"]
    if open_work.get("available"):
        lines.append(
            f"Open work: {open_work['total']} PR(s), {open_work['draft']} draft, {open_work['ready']} ready."
        )
        for item in open_work["previews"]:
            lines.append(f"- #{item['number']} {item['title']}")
        if open_work["total"]:
            lines.append("Open and draft PRs are previews only. Updates install stable releases, never moving branches.")
    else:
        lines.append("Open work details are unavailable; this does not affect stable release updates.")
    if not report["repository"].get("available"):
        lines.append("Repository distance details are unavailable; the runtime result above is authoritative.")
    return "\n".join(lines)


def emit_error(error: BootstrapError, json_output: bool) -> int:
    payload = {"schema": UPDATE_SCHEMA, "ok": False, "error": {"code": error.code, "message": error.message}}
    if json_output:
        json.dump(payload, sys.stderr, ensure_ascii=True, indent=2, sort_keys=True)
        sys.stderr.write("\n")
    else:
        sys.stderr.write(f"MegaBrain update failed: {error.message}\n")
    return 2


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command != "update":
        parser.error("unknown command")
    try:
        report = update_report(args)
    except BootstrapError as error:
        return emit_error(error, args.json_output)
    if args.json_output:
        json.dump(report, sys.stdout, ensure_ascii=True, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(format_update(report) + "\n")
    return 3 if report["approval_required"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
