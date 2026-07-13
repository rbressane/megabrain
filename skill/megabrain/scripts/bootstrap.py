#!/usr/bin/env python3
"""Consumer onboarding for a private, local-first MegaBrain."""

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
from typing import Any


START_MARKER = "<!-- MEGABRAIN:START -->"
END_MARKER = "<!-- MEGABRAIN:END -->"
CONFIG_SCHEMA = "megabrain.user.v1"
HARNESS_PATHS = {
    "codex": (".codex/skills/megabrain", ".codex/AGENTS.md"),
    "claude": (".claude/skills/megabrain", ".claude/CLAUDE.md"),
    "hermes": (".hermes/skills/megabrain", ".hermes/SOUL.md"),
}
GITHUB_REMOTE = re.compile(
    r"(?:git@github\.com:|ssh://git@github\.com/|https://(?:[^@/]+@)?github\.com/)"
    r"(?P<repository>[^/]+/[^/.]+)(?:\.git)?$"
)


class BootstrapError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def require_command(name: str) -> None:
    if not shutil.which(name):
        raise BootstrapError("REQUIREMENT_MISSING", f"MegaBrain requires {name} to be available.")


def invoked_skill_root() -> Path:
    return Path(os.path.abspath(__file__)).parents[1]


def source_skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def detect_harness(explicit: str | None) -> str:
    if explicit:
        return explicit
    configured = os.environ.get("MEGABRAIN_HARNESS", "").lower()
    if configured in HARNESS_PATHS:
        return configured
    parts = set(invoked_skill_root().parts)
    for harness in HARNESS_PATHS:
        if f".{harness}" in parts:
            return harness
    if any(os.environ.get(name) for name in ("CODEX_HOME", "CODEX_THREAD_ID", "CODEX_CI")):
        return "codex"
    if any(os.environ.get(name) for name in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CONFIG_DIR")):
        return "claude"
    if any(os.environ.get(name) for name in ("HERMES_HOME", "HERMES_AGENT_HOME")):
        return "hermes"
    raise BootstrapError(
        "HARNESS_REQUIRED",
        "The agent environment could not be detected automatically. The active agent should supply its harness.",
    )


def config_path(home: Path) -> Path:
    return home / ".megabrain" / "config.json"


def load_config(home: Path, required: bool = False) -> dict[str, Any]:
    path = config_path(home)
    if not path.exists():
        if required:
            raise BootstrapError("SETUP_REQUIRED", "MegaBrain has not been set up for this user yet.")
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise BootstrapError("CONFIG_INVALID", "The local MegaBrain configuration is invalid.") from error
    if not isinstance(value, dict) or value.get("schema") != CONFIG_SCHEMA or not isinstance(value.get("clones", {}), dict):
        raise BootstrapError("CONFIG_INVALID", "The local MegaBrain configuration is invalid.")
    if re.match(r"https?://[^/@\s]+@", str(value.get("remote", ""))):
        raise BootstrapError("CONFIG_INVALID", "Repository URLs containing credentials are forbidden.")
    return value


def save_config(home: Path, value: dict[str, Any]) -> None:
    path = config_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def github_repository(remote: str) -> str | None:
    match = GITHUB_REMOTE.search(remote)
    return match.group("repository") if match else None


def github_auth() -> str:
    require_command("gh")
    auth = run(["gh", "auth", "status", "--hostname", "github.com"])
    if auth.returncode != 0:
        raise BootstrapError(
            "GITHUB_AUTH_REQUIRED",
            "GitHub authorization is required. Approve GitHub access, then retry MegaBrain setup.",
        )
    login = run(["gh", "api", "user", "--jq", ".login"])
    if login.returncode != 0 or not login.stdout.strip():
        raise BootstrapError("GITHUB_AUTH_REQUIRED", "The authenticated GitHub account could not be identified.")
    run(["gh", "auth", "setup-git"], None)
    return login.stdout.strip()


def github_remote_for(repository: str) -> str:
    viewed = run(["gh", "repo", "view", repository, "--json", "visibility,url,sshUrl"])
    if viewed.returncode != 0:
        raise BootstrapError("REPOSITORY_UNAVAILABLE", "The private MegaBrain repository could not be accessed.")
    try:
        details = json.loads(viewed.stdout)
    except json.JSONDecodeError as error:
        raise BootstrapError("REPOSITORY_UNAVAILABLE", "GitHub returned invalid repository metadata.") from error
    if str(details.get("visibility", "")).upper() != "PRIVATE":
        raise BootstrapError("REPOSITORY_NOT_PRIVATE", "MegaBrain refuses to use a non-private repository.")
    protocol = run(["gh", "config", "get", "git_protocol", "--host", "github.com"])
    if protocol.returncode == 0 and protocol.stdout.strip() == "ssh":
        return str(details["sshUrl"])
    return str(details["url"]).rstrip("/") + ".git"


def resolve_repository(
    home: Path,
    requested: str | None,
    allow_local: bool,
) -> tuple[str, str, bool]:
    existing = load_config(home)
    if requested:
        if re.match(r"https?://[^/@\s]+@", requested):
            raise BootstrapError("REPOSITORY_INVALID", "Repository URLs containing credentials are forbidden.")
        if allow_local and not github_repository(requested):
            if existing.get("remote") and normalize_remote(str(existing["remote"])) != normalize_remote(requested):
                raise BootstrapError("REPOSITORY_MISMATCH", "MegaBrain is already configured for a different repository.")
            return requested, str(Path(requested).expanduser().resolve()), False
        repository = github_repository(requested) or requested.removesuffix(".git")
        if "/" not in repository:
            raise BootstrapError("REPOSITORY_INVALID", "The GitHub repository must use owner/name form.")
        if existing.get("remote") and normalize_remote(str(existing["remote"])) != normalize_remote(requested):
            raise BootstrapError("REPOSITORY_MISMATCH", "MegaBrain is already configured for a different repository.")
        github_auth()
        return repository, github_remote_for(repository), False
    if existing.get("repository") and existing.get("remote"):
        repository = str(existing["repository"])
        remote = str(existing["remote"])
        if github_repository(remote):
            github_auth()
            remote = github_remote_for(repository)
        return repository, remote, False
    login = github_auth()
    repository = f"{login}/megabrain"
    viewed = run(["gh", "repo", "view", repository, "--json", "visibility"])
    created = False
    if viewed.returncode != 0:
        created_result = run(
            [
                "gh",
                "repo",
                "create",
                repository,
                "--private",
                "--disable-issues",
                "--disable-wiki",
                "--description",
                "Private local-first Markdown memory for trusted AI agents",
            ]
        )
        if created_result.returncode != 0:
            raise BootstrapError("REPOSITORY_CREATE_FAILED", "GitHub could not create the private MegaBrain repository.")
        created = True
    return repository, github_remote_for(repository), created


def normalize_remote(value: str) -> str:
    repository = github_repository(value)
    if repository:
        return repository.lower()
    path = Path(value).expanduser()
    return str(path.resolve()) if path.exists() or value.startswith(('.', '/')) else value.rstrip("/")


def clone_path(home: Path, harness: str) -> Path:
    return home / ".megabrain" / "clones" / harness


def is_empty_repository(root: Path) -> bool:
    result = run(["git", "rev-parse", "--verify", "HEAD"], root)
    return result.returncode != 0


def copy_seed(root: Path) -> None:
    seed = source_skill_root() / "seed"
    if not seed.exists():
        raise BootstrapError("SEED_MISSING", "The MegaBrain installation seed is missing.")
    for source in sorted(seed.rglob("*")):
        if source.is_dir():
            continue
        destination = root / source.relative_to(seed)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    destination_skill = root / "skill" / "megabrain"
    shutil.copytree(
        source_skill_root(),
        destination_skill,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("seed", "__pycache__", "*.pyc"),
    )


def configure_git(root: Path, name: str, identity_id: str | None = None) -> None:
    suffix = identity_id or "bootstrap"
    run(["git", "config", "user.name", name], root)
    run(["git", "config", "user.email", f"megabrain+{suffix}@users.noreply.github.com"], root)


def seed_repository(root: Path) -> None:
    copy_seed(root)
    run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], root)
    configure_git(root, "MegaBrain Bootstrap")
    added = run(["git", "add", "."], root)
    committed = run(["git", "commit", "-m", "feat: initialize private MegaBrain"], root)
    if added.returncode != 0 or committed.returncode != 0:
        raise BootstrapError("SEED_COMMIT_FAILED", "The initial private brain could not be committed.")
    pushed = run(["git", "push", "-u", "origin", "main"], root)
    if pushed.returncode != 0:
        raise BootstrapError("SEED_PUSH_FAILED", "The initial private brain could not be synchronized to GitHub.")


def assert_clean(root: Path) -> None:
    status = run(["git", "status", "--porcelain", "--untracked-files=all"], root)
    if status.returncode != 0:
        raise BootstrapError("CLONE_INVALID", "The managed MegaBrain clone is not a Git repository.")
    changed = [line[3:] for line in status.stdout.splitlines() if line.strip()]
    if changed:
        raise BootstrapError("CLONE_DIRTY", "The managed MegaBrain clone has unexpected local edits.")


def ensure_clone(home: Path, harness: str, remote: str) -> tuple[Path, bool]:
    root = clone_path(home, harness)
    created = False
    if root.exists():
        if not (root / ".git").exists():
            raise BootstrapError("CLONE_PATH_OCCUPIED", "MegaBrain's managed location is occupied by another folder.")
        existing_remote = run(["git", "remote", "get-url", "origin"], root)
        if existing_remote.returncode != 0 or normalize_remote(existing_remote.stdout.strip()) != normalize_remote(remote):
            raise BootstrapError("CLONE_REMOTE_MISMATCH", "The managed clone points to a different repository.")
        assert_clean(root)
    else:
        root.parent.mkdir(parents=True, exist_ok=True)
        cloned = run(["git", "clone", remote, str(root)], root.parent)
        if cloned.returncode != 0:
            raise BootstrapError("CLONE_FAILED", "The private MegaBrain repository could not be cloned.")
        created = True
    if is_empty_repository(root):
        seed_repository(root)
    else:
        remote_main = run(["git", "ls-remote", "--heads", "origin", "main"], root)
        if remote_main.returncode == 0 and not remote_main.stdout.strip():
            pushed = run(["git", "push", "-u", "origin", "HEAD:main"], root)
            if pushed.returncode != 0:
                raise BootstrapError("SEED_PUSH_FAILED", "The initial private brain could not be synchronized to GitHub.")
        fetched = run(["git", "fetch", "origin", "main"], root)
        rebased = run(["git", "rebase", "origin/main"], root) if fetched.returncode == 0 else fetched
        if rebased.returncode != 0:
            run(["git", "rebase", "--abort"], root)
            raise BootstrapError("SYNC_FAILED", "The private MegaBrain repository could not be synchronized.")
    return root, created


def record_text(meta: dict[str, object], body: str) -> str:
    return f"<!-- megabrain-meta\n{json.dumps(meta, indent=2, sort_keys=True)}\n-->\n\n{body.strip()}\n"


def load_or_create_identity(root: Path, harness: str, display_name: str) -> tuple[dict[str, str], bool]:
    path = root / ".megabrain" / "local.json"
    if path.exists():
        try:
            identity = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise BootstrapError("IDENTITY_INVALID", "The local agent identity is invalid.") from error
        if identity.get("harness") != harness:
            raise BootstrapError("IDENTITY_MISMATCH", "This clone belongs to another agent harness.")
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


def push_with_retry(root: Path) -> bool:
    for _ in range(3):
        pushed = run(["git", "push", "origin", "HEAD:main"], root)
        if pushed.returncode == 0:
            return True
        fetched = run(["git", "fetch", "origin", "main"], root)
        rebased = run(["git", "rebase", "origin/main"], root) if fetched.returncode == 0 else fetched
        if rebased.returncode != 0:
            run(["git", "rebase", "--abort"], root)
            return False
    return False


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
    run(["git", "add", "--", str(registry.relative_to(root))], root)
    committed = run(["git", "commit", "-m", f"agent: register {identity['harness']} {identity['id']}"], root)
    if committed.returncode != 0:
        registry.unlink(missing_ok=True)
        raise BootstrapError("AGENT_COMMIT_FAILED", "The agent identity could not be registered.")
    if not push_with_retry(root):
        print("MegaBrain: agent registered locally; synchronization is pending.", file=sys.stderr)
    return True


def instruction_block(command_path: Path) -> str:
    helper = f'python3 "{command_path}"'
    return f"""{START_MARKER}
## MegaBrain

Before every user request, retrieve private task context:

```sh
printf '%s' '{{"task":"brief description of the current user request"}}' | {helper} context --stdin
```

Use relevant current memories privately. Surface every relevant conflicting claim and ask for clarification. Continue from local state during outages and mention staleness only when material.

Before finishing, capture only new durable facts, preferences, decisions, commitments, project state, corrections, or resource pointers with `{helper} remember --stdin`. Never store raw chat, transient work, credentials, or secret values. Show compact `MegaBrain:` save notices. Use `correct`, `forget`, or `ingest` for those explicit operations.
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


def install_skill(home: Path, harness: str, target: Path) -> tuple[Path, bool]:
    link_rel, _ = HARNESS_PATHS[harness]
    link = home / link_rel
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        if link.resolve() != target.resolve():
            link.unlink()
            link.symlink_to(target)
        return link, True
    if link.exists():
        if link.resolve() == invoked_skill_root().resolve():
            return link, False
        raise BootstrapError("SKILL_PATH_OCCUPIED", "The agent's MegaBrain skill path is occupied by another installation.")
    link.symlink_to(target)
    return link, True


def validate_clone(root: Path) -> dict[str, Any]:
    helper = root / "skill" / "megabrain" / "scripts" / "megabrain.py"
    if not helper.exists():
        raise BootstrapError("REPOSITORY_INVALID", "The selected repository is not a MegaBrain repository.")
    validated = run([sys.executable, str(helper), "validate"], root)
    try:
        result = json.loads(validated.stdout)
    except json.JSONDecodeError as error:
        raise BootstrapError("VALIDATION_FAILED", "MegaBrain validation did not return a valid result.") from error
    if validated.returncode != 0 or not result.get("ok"):
        raise BootstrapError("VALIDATION_FAILED", "The private MegaBrain repository failed validation.")
    return result


def setup(args: argparse.Namespace) -> dict[str, Any]:
    require_command("git")
    if sys.version_info < (3, 10):
        raise BootstrapError("PYTHON_UNSUPPORTED", "MegaBrain requires Python 3.10 or newer.")
    home = args.home.expanduser().resolve()
    harness = detect_harness(args.harness)
    repository, remote, repository_created = resolve_repository(home, args.repository, args.allow_local_remote)
    root, clone_created = ensure_clone(home, harness, remote)
    validation = validate_clone(root)
    display_name = args.display_name or f"{harness.title()} on {os.uname().nodename}"
    identity, identity_created = load_or_create_identity(root, harness, display_name)
    configure_git(root, f"MegaBrain {identity['display_name']}", identity["id"])
    registered = register_agent(root, identity)
    link, linked = install_skill(home, harness, root / "skill" / "megabrain")
    _, instructions_rel = HARNESS_PATHS[harness]
    replace_block(home / instructions_rel, instruction_block(link / "scripts" / "megabrain.py"))
    config = load_config(home)
    if not config:
        config = {"schema": CONFIG_SCHEMA, "created_at": utc_now(), "clones": {}}
    config.update({"repository": repository, "remote": remote})
    config.setdefault("clones", {})[harness] = str(root)
    save_config(home, config)
    validation = validate_clone(root)
    browser: dict[str, Any] | None = None
    if not args.no_open:
        browsed = run([sys.executable, str(root / "skill" / "megabrain" / "scripts" / "megabrain.py"), "browse"], root)
        if browsed.stdout.strip():
            try:
                browser = json.loads(browsed.stdout)
            except json.JSONDecodeError:
                browser = {"generated": False, "opened": False}
    return {
        "ok": True,
        "message": "MegaBrain is ready.",
        "harness": harness,
        "repository": repository,
        "repository_created": repository_created,
        "clone_created": clone_created,
        "identity_created": identity_created,
        "registered": registered,
        "skill_linked": linked,
        "agent_id": identity["id"],
        "counts": validation["counts"],
        "browser": browser,
    }


def status(args: argparse.Namespace) -> dict[str, Any]:
    home = args.home.expanduser().resolve()
    harness = detect_harness(args.harness)
    config = load_config(home, required=True)
    root_value = config.get("clones", {}).get(harness)
    if not root_value:
        return {"ok": True, "ready": False, "harness": harness, "message": "MegaBrain is not connected to this agent."}
    root = Path(str(root_value)).expanduser().resolve()
    identity_path = root / ".megabrain" / "local.json"
    validation = validate_clone(root)
    sync = run([sys.executable, str(root / "skill" / "megabrain" / "scripts" / "megabrain.py"), "sync"], root)
    try:
        sync_result = json.loads(sync.stdout)
    except json.JSONDecodeError:
        sync_result = {"synced": False, "stale": True, "reason": "status_unavailable"}
    return {
        "ok": True,
        "ready": identity_path.exists() and validation["ok"],
        "harness": harness,
        "repository": config.get("repository"),
        "counts": validation["counts"],
        "sync": sync_result,
        "message": "MegaBrain is ready." if identity_path.exists() else "MegaBrain needs repair.",
    }


def open_brain(args: argparse.Namespace) -> dict[str, Any]:
    home = args.home.expanduser().resolve()
    harness = detect_harness(args.harness)
    config = load_config(home, required=True)
    root_value = config.get("clones", {}).get(harness)
    if not root_value:
        raise BootstrapError("SETUP_REQUIRED", "MegaBrain is not connected to this agent.")
    root = Path(str(root_value)).expanduser().resolve()
    helper = root / "skill" / "megabrain" / "scripts" / "megabrain.py"
    command = [sys.executable, str(helper), "browse"]
    if args.no_open:
        command.append("--no-open")
    browsed = run(command, root)
    output = browsed.stdout if browsed.stdout.strip() else browsed.stderr
    try:
        result = json.loads(output)
    except json.JSONDecodeError as error:
        raise BootstrapError("BROWSER_FAILED", "MegaBrain could not open the local browser.") from error
    if browsed.returncode != 0:
        raise BootstrapError("BROWSER_FAILED", "MegaBrain could not open the local browser.")
    result["message"] = "MegaBrain is open." if result.get("opened") else "MegaBrain browser is ready."
    return result


def disconnect(args: argparse.Namespace) -> dict[str, Any]:
    home = args.home.expanduser().resolve()
    harness = detect_harness(args.harness)
    config = load_config(home, required=True)
    root_value = config.get("clones", {}).get(harness)
    root = Path(str(root_value)).expanduser().resolve() if root_value else clone_path(home, harness)
    link_rel, instructions_rel = HARNESS_PATHS[harness]
    link = home / link_rel
    target = root / "skill" / "megabrain"
    if link.is_symlink() and link.resolve() == target.resolve():
        link.unlink()
    replace_block(home / instructions_rel, None)
    config.setdefault("clones", {}).pop(harness, None)
    save_config(home, config)
    return {
        "ok": True,
        "message": "MegaBrain is disconnected from this agent.",
        "harness": harness,
        "local_clone_retained": root.exists(),
        "repository_retained": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Set up and manage MegaBrain without manual Git operations")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("setup", "connect"):
        action = subparsers.add_parser(command)
        action.add_argument("--harness", choices=sorted(HARNESS_PATHS))
        action.add_argument("--display-name")
        action.add_argument("--repository")
        action.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
        action.add_argument("--allow-local-remote", action="store_true", help=argparse.SUPPRESS)
        action.add_argument("--no-open", action="store_true", help=argparse.SUPPRESS)
    for command in ("status", "open", "disconnect"):
        action = subparsers.add_parser(command)
        action.add_argument("--harness", choices=sorted(HARNESS_PATHS))
        action.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
        if command == "open":
            action.add_argument("--no-open", action="store_true", help=argparse.SUPPRESS)
    return parser


def emit(value: dict[str, Any], stream: Any = sys.stdout) -> None:
    json.dump(value, stream, ensure_ascii=True, indent=2, sort_keys=True)
    stream.write("\n")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command in {"setup", "connect"}:
            result = setup(args)
        elif args.command == "status":
            result = status(args)
        elif args.command == "open":
            result = open_brain(args)
        elif args.command == "disconnect":
            result = disconnect(args)
        else:
            parser.error("unknown command")
            return 2
        emit(result)
        return 0 if result.get("ok") else 1
    except BootstrapError as error:
        emit({"ok": False, "error": {"code": error.code, "message": error.message}}, sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
