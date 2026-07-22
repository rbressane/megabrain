#!/usr/bin/env python3
"""First-class consumer command for MegaBrain runtime operations."""

from __future__ import annotations

import argparse
import json
import re
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
from megabrain import ROLE_LINE_PATTERN, detect_secret, strings_in


UPDATE_SCHEMA = "megabrain.update.v1"
PRODUCT_CATEGORIES = {
    "acceptance_test",
    "behavior_documentation_mismatch",
    "cross_agent_capability",
    "documentation_gap",
    "install_update_migration_recovery",
    "missing_command",
    "product_ux_policy",
    "repeated_workaround",
    "retrieval_correction_privacy_security_failure",
}
FEEDBACK_REQUIRED = {
    "category",
    "title",
    "mission",
    "observation",
    "why_product",
    "current_behavior",
    "expected_behavior",
    "reproduction",
    "scope",
    "acceptance_criteria",
    "tests",
    "documentation",
    "release_notes",
    "evidence",
}
PRIVATE_PATH_PATTERN = re.compile(r"(?:^|\s)(?:/Users/|/home/|[A-Za-z]:\\Users\\)")
PRIVATE_URL_PATTERN = re.compile(
    r"https?://(?:localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|[^/\s]+\.local)(?:[/:]|$)",
    re.IGNORECASE,
)


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
    feedback = subparsers.add_parser("feedback", help="render a sanitized Product Bake Candidate offline")
    feedback.add_argument("--stdin", action="store_true", help="read the structured candidate from stdin")
    feedback.add_argument("--output", type=Path, help="also write to a new explicit local file")
    return parser


def read_feedback_input() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        raise BootstrapError("FEEDBACK_INPUT_REQUIRED", "Expected a JSON object on stdin.")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise BootstrapError("FEEDBACK_INVALID_JSON", f"Input must be valid JSON near line {error.lineno}.") from error
    if not isinstance(value, dict):
        raise BootstrapError("FEEDBACK_INVALID_INPUT", "Feedback input must be a JSON object.")
    return value


def require_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise BootstrapError("FEEDBACK_INVALID_INPUT", f"Field `{field}` must be non-empty text.")
    return value.strip()


def require_list(payload: dict[str, Any], field: str) -> list[str]:
    value = payload.get(field)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        raise BootstrapError("FEEDBACK_INVALID_INPUT", f"Field `{field}` must be a non-empty list of text values.")
    return [item.strip() for item in value]


def render_block(value: str | list[str]) -> str:
    if isinstance(value, str):
        return value.strip()
    return "\n".join(f"- {item}" for item in value)


def validate_feedback(payload: dict[str, Any]) -> dict[str, str | list[str]]:
    missing = sorted(FEEDBACK_REQUIRED - set(payload))
    if missing:
        raise BootstrapError("FEEDBACK_INVALID_INPUT", f"Missing required fields: {', '.join(missing)}.")
    if payload.get("category") not in PRODUCT_CATEGORIES:
        raise BootstrapError(
            "NOT_PRODUCT_BAKE_CANDIDATE",
            "The finding category is private, transient, local-only, already resolved, or not product-wide.",
        )
    transcript_lines = sum(len(ROLE_LINE_PATTERN.findall(text)) for text in strings_in(payload))
    if transcript_lines >= 2:
        raise BootstrapError("FEEDBACK_TRANSCRIPT_REJECTED", "Raw transcript-shaped feedback is not accepted.")
    if detect_secret(payload):
        raise BootstrapError("FEEDBACK_SECRET_REJECTED", "Likely secret material cannot be included in product feedback.")
    if any(PRIVATE_PATH_PATTERN.search(text) for text in strings_in(payload)):
        raise BootstrapError("FEEDBACK_PRIVATE_PATH_REJECTED", "Private filesystem paths must be removed or generalized.")
    if any(PRIVATE_URL_PATTERN.search(text) for text in strings_in(payload)):
        raise BootstrapError("FEEDBACK_PRIVATE_URL_REJECTED", "Private URLs must be removed or generalized.")
    if sum(len(text) for text in strings_in(payload)) > 20_000:
        raise BootstrapError("FEEDBACK_TOO_LARGE", "Feedback must be a concise sanitized product brief, not a source dump.")

    values: dict[str, str | list[str]] = {
        field: require_text(payload, field)
        for field in (
            "title", "mission", "observation", "why_product", "current_behavior",
            "expected_behavior", "release_notes",
        )
    }
    for field in ("reproduction", "scope", "acceptance_criteria", "tests", "documentation", "evidence"):
        values[field] = require_list(payload, field)
    supplied_privacy = payload.get("privacy_constraints", [])
    if not isinstance(supplied_privacy, list) or not all(
        isinstance(item, str) and item.strip() for item in supplied_privacy
    ):
        raise BootstrapError("FEEDBACK_INVALID_INPUT", "Field `privacy_constraints` must be a list of text values.")
    mandatory = [
        "Never access a private Brain.",
        "Use synthetic fixtures only.",
        "Never echo rejected secret-like values.",
        "Never transmit or publish feedback automatically.",
    ]
    values["privacy_constraints"] = list(dict.fromkeys([*mandatory, *(item.strip() for item in supplied_privacy)]))
    return values


def render_feedback(payload: dict[str, Any]) -> str:
    values = validate_feedback(payload)
    template = (Path(__file__).resolve().parents[1] / "assets" / "product-bake-candidate.md").read_text(
        encoding="utf-8"
    )
    rendered = template.format(**{field: render_block(value) for field, value in values.items()})
    return rendered.rstrip() + "\n"


def write_feedback(path: Path, rendered: str) -> None:
    destination = path.expanduser().resolve()
    if destination.exists():
        raise BootstrapError("FEEDBACK_OUTPUT_EXISTS", "The explicit feedback output path already exists.")
    if not destination.parent.is_dir():
        raise BootstrapError("FEEDBACK_OUTPUT_INVALID", "The explicit feedback output directory does not exist.")
    destination.write_text(rendered, encoding="utf-8")
    try:
        destination.chmod(0o600)
    except OSError:
        pass


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
    if args.command == "feedback":
        if not args.stdin:
            parser.error("feedback requires --stdin")
        try:
            rendered = render_feedback(read_feedback_input())
            if args.output:
                write_feedback(args.output, rendered)
        except BootstrapError as error:
            sys.stderr.write(f"MegaBrain feedback failed: {error.message}\n")
            return 2
        sys.stdout.write(rendered)
        return 0
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
