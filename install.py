#!/usr/bin/env python3
"""Install or remove MegaBrain integration for one agent environment."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


START_MARKER = "<!-- MEGABRAIN:START -->"
END_MARKER = "<!-- MEGABRAIN:END -->"
HARNESS_PATHS = {
    "codex": (".codex/skills/megabrain", ".codex/AGENTS.md"),
    "claude": (".claude/skills/megabrain", ".claude/CLAUDE.md"),
    "hermes": (".hermes/skills/megabrain", ".hermes/SOUL.md"),
}
GITHUB_REMOTE = re.compile(r"(?:git@|https://)(?:[^@/]+@)?github\.com[/:]([^/]+/[^/.]+)(?:\.git)?$")


class InstallError(Exception):
    pass


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def record_text(meta: dict[str, object], body: str) -> str:
    return f"<!-- megabrain-meta\n{json.dumps(meta, indent=2, sort_keys=True)}\n-->\n\n{body.strip()}\n"


def origin(root: Path) -> str:
    result = run(["git", "remote", "get-url", "origin"], root)
    if result.returncode != 0 or not result.stdout.strip():
        raise InstallError("This managed clone needs an origin remote.")
    return result.stdout.strip()


def verify_remote(root: Path, allow_local: bool, confirm_private: bool) -> None:
    remote = origin(root)
    if allow_local:
        return
    match = GITHUB_REMOTE.search(remote)
    if not match:
        raise InstallError("Origin must be a private GitHub repository.")
    reachable = run(["git", "ls-remote", "--exit-code", "origin", "HEAD"], root)
    if reachable.returncode != 0:
        raise InstallError("Origin is not reachable with the configured Git credentials.")
    repository = match.group(1)
    if shutil.which("gh"):
        viewed = run(["gh", "repo", "view", repository, "--json", "visibility", "--jq", ".visibility"], root)
        if viewed.returncode == 0:
            if viewed.stdout.strip().upper() != "PRIVATE":
                raise InstallError("MegaBrain refuses to install against a non-private GitHub repository.")
            return
    if not confirm_private:
        raise InstallError(
            "GitHub privacy could not be verified. Confirm the repository is private, then rerun with --confirm-private."
        )


def assert_clean(root: Path) -> None:
    status = run(["git", "status", "--porcelain", "--untracked-files=all"], root)
    if status.returncode != 0:
        raise InstallError("The current directory is not a Git working tree.")
    changed = [line[3:] for line in status.stdout.splitlines() if line.strip()]
    if changed:
        raise InstallError("The managed clone has unexpected tracked or untracked edits: " + ", ".join(changed[:5]))


def instruction_block(harness: str, command_path: Path) -> str:
    command = f'python3 "{command_path}"'
    return f"""{START_MARKER}
## MegaBrain

For every user request, retrieve task-specific context before starting:

```sh
printf '%s' '{{"task":"brief description of the current user request"}}' | {command} context --stdin
```

Use returned memories as private context. When `conflicts` is non-empty and relevant, present every claim and ask the user to clarify; never silently select one. If `stale` is true, continue from the local clone and mention possible staleness when it affects the answer.

Before the final response, capture only new durable facts, preferences, decisions, commitments, project state, corrections, or resource pointers. Store each independent item with `{command} remember --stdin`; do not store raw chat, transient work, credentials, or secret values. Show the helper's compact `MegaBrain:` notice when it creates memories. Use `correct`, `forget`, or `ingest` when the user requests those operations.
{END_MARKER}"""


def replace_block(path: Path, block: str | None) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(rf"(?:\n*){re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}(?:\n*)", re.DOTALL)
    text = pattern.sub("\n", text).strip()
    if block:
        text = f"{text}\n\n{block}".strip()
    if text:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    elif path.exists():
        path.unlink()


def install_link(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        if link.resolve() == target.resolve():
            return
        link.unlink()
    elif link.exists():
        raise InstallError(f"Refusing to replace existing non-symlink path: {link}")
    link.symlink_to(target)


def uninstall(link: Path, instructions: Path, target: Path) -> None:
    if link.is_symlink() and link.resolve() == target.resolve():
        link.unlink()
    replace_block(instructions, None)


def load_or_create_identity(root: Path, harness: str, display_name: str) -> tuple[dict[str, str], bool]:
    path = root / ".megabrain" / "local.json"
    if path.exists():
        try:
            identity = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise InstallError("The local MegaBrain identity file is invalid.") from error
        if identity.get("harness") != harness:
            raise InstallError("This managed clone is already assigned to a different harness.")
        return identity, False
    identity = {
        "id": str(uuid.uuid4()),
        "harness": harness,
        "display_name": display_name,
        "created_at": utc_now(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return identity, True


def register_agent(root: Path, identity: dict[str, str]) -> bool:
    registry = root / "brain" / "agents" / f"{identity['id']}.md"
    if registry.exists():
        return False
    meta = {
        "schema": "megabrain.agent.v1",
        "id": identity["id"],
        "harness": identity["harness"],
        "display_name": identity["display_name"],
        "created_at": identity["created_at"],
    }
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        record_text(meta, f"# Agent: {identity['display_name']}\n\nProvenance identity for a trusted {identity['harness']} environment."),
        encoding="utf-8",
    )
    added = run(["git", "add", "--", str(registry.relative_to(root))], root)
    committed = run(["git", "commit", "-m", f"agent: register {identity['harness']} {identity['id']}"], root)
    if added.returncode != 0 or committed.returncode != 0:
        registry.unlink(missing_ok=True)
        raise InstallError("Could not commit the agent registry entry.")
    pushed = run(["git", "push", "origin", "HEAD:main"], root)
    if pushed.returncode != 0:
        for _ in range(3):
            fetched = run(["git", "fetch", "origin", "main"], root)
            rebased = run(["git", "rebase", "origin/main"], root) if fetched.returncode == 0 else fetched
            if rebased.returncode != 0:
                run(["git", "rebase", "--abort"], root)
                continue
            pushed = run(["git", "push", "origin", "HEAD:main"], root)
            if pushed.returncode == 0:
                break
    if pushed.returncode != 0:
        print("MegaBrain: agent registered locally; synchronization is pending.", file=sys.stderr)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Install MegaBrain into one agent environment")
    parser.add_argument("--harness", required=True, choices=sorted(HARNESS_PATHS))
    parser.add_argument("--display-name")
    parser.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--confirm-private", action="store_true")
    parser.add_argument("--allow-local-remote", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    home = args.home.expanduser().resolve()
    skill_target = root / "skill" / "megabrain"
    link_rel, instructions_rel = HARNESS_PATHS[args.harness]
    link = home / link_rel
    instructions = home / instructions_rel

    try:
        if args.uninstall:
            uninstall(link, instructions, skill_target)
            print(f"MegaBrain: removed managed {args.harness} integration.")
            return 0
        assert_clean(root)
        verify_remote(root, args.allow_local_remote, args.confirm_private)
        display_name = args.display_name or f"{args.harness.title()} on {os.uname().nodename}"
        identity, _ = load_or_create_identity(root, args.harness, display_name)
        run(["git", "config", "user.name", f"MegaBrain {identity['display_name']}"], root)
        run(["git", "config", "user.email", f"megabrain+{identity['id']}@users.noreply.github.com"], root)
        run(["git", "fetch", "origin", "main"], root)
        rebased = run(["git", "rebase", "origin/main"], root)
        if rebased.returncode != 0:
            run(["git", "rebase", "--abort"], root)
            raise InstallError("Could not synchronize the clean managed clone before registration.")
        registered = register_agent(root, identity)
        install_link(link, skill_target)
        replace_block(instructions, instruction_block(args.harness, link / "scripts" / "megabrain.py"))
        state = "registered" if registered else "already registered"
        print(f"MegaBrain: installed for {args.harness}; agent {state} as {identity['id']}.")
        return 0
    except InstallError as error:
        print(f"MegaBrain install error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
