#!/usr/bin/env python3
"""Consumer onboarding and versioned runtime management for MegaBrain."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


START_MARKER = "<!-- MEGABRAIN:START -->"
END_MARKER = "<!-- MEGABRAIN:END -->"
CONFIG_SCHEMA = "megabrain.user.v1"
RUNTIME_SCHEMA = "megabrain.runtime.v1"
BRAIN_SCHEMA = "megabrain.brain.v1"
OFFICIAL_DISTRIBUTION = "https://github.com/rbressane/megabrain.git"
UPDATE_INTERVAL = timedelta(hours=24)
SETUP_READY_MESSAGE = (
    "MegaBrain is ready.\n"
    "Say \"Synchronize and open my MegaBrain\" anytime to synchronize, validate, "
    "and browse your private Brain locally."
)
HARNESS_PATHS = {
    "codex": (".codex/skills/megabrain", ".codex/AGENTS.md"),
    "claude": (".claude/skills/megabrain", ".claude/CLAUDE.md"),
    "hermes": (".hermes/skills/megabrain", ".hermes/SOUL.md"),
}
GITHUB_REMOTE = re.compile(
    r"(?:git@github\.com:|ssh://git@github\.com/|https://(?:[^@/]+@)?github\.com/)"
    r"(?P<repository>[^/]+/[^/.]+)(?:\.git)?$"
)
VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
LEGACY_SEED_WORKFLOW_PATH = Path(".github/workflows/validate.yml")
LEGACY_SEED_WORKFLOW = b"""name: Validate MegaBrain

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: rbressane/megabrain/.github/actions/validate-brain@v1.0.0
"""


class BootstrapError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def run(
    command: list[str],
    cwd: Path | None = None,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, **(env or {})},
    )


def require_command(name: str) -> None:
    if not shutil.which(name):
        raise BootstrapError("REQUIREMENT_MISSING", f"MegaBrain requires {name} to be available.")


def source_skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def source_distribution_root() -> Path | None:
    candidate = source_skill_root().parents[1]
    return candidate if (candidate / ".git").exists() else None


def detect_harness(explicit: str | None) -> str:
    if explicit:
        return explicit
    configured = os.environ.get("MEGABRAIN_HARNESS", "").lower()
    if configured in HARNESS_PATHS:
        return configured
    invoked = Path(os.path.abspath(__file__))
    for harness in HARNESS_PATHS:
        if f".{harness}" in invoked.parts:
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


def update_state_path(home: Path) -> Path:
    return home / ".megabrain" / "update-state.json"


def load_json(path: Path, code: str, message: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise BootstrapError(code, message) from error
    if not isinstance(value, dict):
        raise BootstrapError(code, message)
    return value


def load_config(home: Path, required: bool = False) -> dict[str, Any]:
    path = config_path(home)
    if not path.exists():
        if required:
            raise BootstrapError("SETUP_REQUIRED", "MegaBrain has not been set up for this user yet.")
        return {}
    value = load_json(path, "CONFIG_INVALID", "The local MegaBrain configuration is invalid.")
    if value.get("schema") != CONFIG_SCHEMA or not isinstance(value.get("clones", {}), dict):
        raise BootstrapError("CONFIG_INVALID", "The local MegaBrain configuration is invalid.")
    for remote in (value.get("remote"), value.get("runtime", {}).get("source") if isinstance(value.get("runtime"), dict) else None):
        if remote and re.match(r"https?://[^/@\s]+@", str(remote)):
            raise BootstrapError("CONFIG_INVALID", "Repository URLs containing credentials are forbidden.")
    return value


def save_private_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def save_config(home: Path, value: dict[str, Any]) -> None:
    save_private_json(config_path(home), value)


def semantic_version(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    match = VERSION_PATTERN.fullmatch(value)
    return tuple(map(int, match.groups())) if match else None


def runtime_metadata(skill_root: Path) -> dict[str, Any]:
    value = load_json(skill_root / "runtime.json", "RUNTIME_INVALID", "MegaBrain runtime metadata is invalid.")
    if (
        value.get("schema") != RUNTIME_SCHEMA
        or semantic_version(value.get("version")) is None
        or not isinstance(value.get("protocol_version"), int)
        or value.get("automatic_updates") not in {"compatible", "disabled"}
    ):
        raise BootstrapError("RUNTIME_INVALID", "MegaBrain runtime metadata is invalid.")
    return value


def brain_metadata(root: Path) -> dict[str, Any]:
    value = load_json(root / "megabrain.json", "BRAIN_MANIFEST_INVALID", "The brain compatibility manifest is invalid.")
    if (
        value.get("schema") != BRAIN_SCHEMA
        or not isinstance(value.get("protocol_version"), int)
        or semantic_version(value.get("minimum_runtime")) is None
    ):
        raise BootstrapError("BRAIN_MANIFEST_INVALID", "The brain compatibility manifest is invalid.")
    return value


def runtime_base(home: Path) -> Path:
    return home / ".megabrain" / "runtime"


def runtime_release(home: Path, version: str) -> Path:
    return runtime_base(home) / "releases" / version.removeprefix("v")


def current_runtime(home: Path) -> Path:
    return runtime_base(home) / "current"


def validate_runtime_release(root: Path, expected_version: str | None = None) -> dict[str, Any]:
    skill = root / "skill" / "megabrain"
    metadata = runtime_metadata(skill)
    version = str(metadata["version"])
    if expected_version and version != expected_version.removeprefix("v"):
        raise BootstrapError("RUNTIME_VERSION_MISMATCH", "The release metadata does not match its version tag.")
    for relative in (
        "SKILL.md",
        "scripts/cli.py",
        "scripts/megabrain.py",
        "scripts/bootstrap.py",
        "assets/browser.html",
        "assets/product-bake-candidate.md",
    ):
        path = skill / relative
        if not path.is_file():
            raise BootstrapError("RUNTIME_INVALID", "The MegaBrain runtime is incomplete.")
    for path in skill.rglob("*.py"):
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except (OSError, SyntaxError) as error:
            raise BootstrapError("RUNTIME_INVALID", "The MegaBrain runtime failed validation.") from error
    return metadata


def copy_runtime_release(source_skill: Path, target: Path) -> dict[str, Any]:
    metadata = runtime_metadata(source_skill)
    if target.exists():
        return validate_runtime_release(target, str(metadata["version"]))
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{target.name}-{uuid.uuid4().hex}"
    try:
        (staging / "skill").mkdir(parents=True)
        shutil.copytree(
            source_skill,
            staging / "skill" / "megabrain",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        validate_runtime_release(staging, str(metadata["version"]))
        staging.rename(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return metadata


def activate_runtime(home: Path, version: str) -> Path:
    target = runtime_release(home, version)
    validate_runtime_release(target, version)
    current = current_runtime(home)
    current.parent.mkdir(parents=True, exist_ok=True)
    temporary = current.parent / f".current-{uuid.uuid4().hex}"
    temporary.symlink_to(Path("releases") / version.removeprefix("v"))
    if current.exists() and not current.is_symlink():
        temporary.unlink(missing_ok=True)
        raise BootstrapError("RUNTIME_PATH_OCCUPIED", "MegaBrain's runtime location is occupied by another folder.")
    os.replace(temporary, current)
    return current


def command_path(home: Path) -> Path:
    return home / ".local" / "bin" / "megabrain"


def command_target(home: Path) -> Path:
    return current_runtime(home) / "skill" / "megabrain" / "scripts" / "cli.py"


def command_is_managed(home: Path, path: Path) -> bool:
    if not path.is_symlink():
        return False
    try:
        target = path.resolve(strict=False)
    except OSError:
        return False
    return runtime_base(home) in target.parents


def install_command(home: Path) -> dict[str, Any]:
    path = command_path(home)
    target = command_target(home)
    if path.is_symlink() or path.exists():
        if not command_is_managed(home, path):
            raise BootstrapError(
                "COMMAND_PATH_OCCUPIED",
                "A different executable already uses MegaBrain's command path.",
            )
        if path.is_symlink() and Path(os.readlink(path)) == target:
            changed = False
        else:
            path.unlink()
            path.symlink_to(target)
            changed = True
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)
        changed = True
    path_entries = {
        Path(entry).expanduser().resolve()
        for entry in os.environ.get("PATH", "").split(os.pathsep)
        if entry
    }
    on_path = path.parent.resolve() in path_entries
    return {
        "path": str(path),
        "installed": True,
        "changed": changed,
        "on_path": on_path,
        "path_notice": None if on_path else 'Run `export PATH="$HOME/.local/bin:$PATH"` before using `megabrain` in this shell.',
    }


def source_remote(requested: str | None) -> str:
    remote = requested or os.environ.get("MEGABRAIN_DISTRIBUTION")
    root = source_distribution_root()
    if not remote and root:
        result = run(["git", "remote", "get-url", "origin"], root)
        if result.returncode == 0 and result.stdout.strip():
            remote = result.stdout.strip()
    remote = remote or OFFICIAL_DISTRIBUTION
    if re.match(r"https?://[^/@\s]+@", remote):
        raise BootstrapError("DISTRIBUTION_INVALID", "Distribution URLs containing credentials are forbidden.")
    if not requested and not os.environ.get("MEGABRAIN_DISTRIBUTION"):
        repository = github_repository(remote)
        if repository and repository.lower() != "rbressane/megabrain":
            raise BootstrapError("DISTRIBUTION_UNTRUSTED", "MegaBrain must be installed from the official repository.")
    return remote


def install_runtime(home: Path, distribution: str | None) -> tuple[Path, dict[str, Any], str]:
    source = source_skill_root()
    metadata = runtime_metadata(source)
    version = str(metadata["version"])
    target = runtime_release(home, version)
    copy_runtime_release(source, target)
    current = activate_runtime(home, version)
    return current, metadata, source_remote(distribution)


def github_repository(remote: str) -> str | None:
    match = GITHUB_REMOTE.search(remote)
    return match.group("repository") if match else None


def github_auth() -> str:
    require_command("gh")
    if run(["gh", "auth", "status", "--hostname", "github.com"]).returncode != 0:
        raise BootstrapError(
            "GITHUB_AUTH_REQUIRED",
            "GitHub authorization is required. Approve GitHub access, then retry MegaBrain setup.",
        )
    login = run(["gh", "api", "user", "--jq", ".login"])
    if login.returncode != 0 or not login.stdout.strip():
        raise BootstrapError("GITHUB_AUTH_REQUIRED", "The authenticated GitHub account could not be identified.")
    run(["gh", "auth", "setup-git"])
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


def resolve_repository(home: Path, requested: str | None, allow_local: bool) -> tuple[str, str, bool]:
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
    repository = f"{login}/megabrain-data"
    viewed = run(["gh", "repo", "view", repository, "--json", "visibility"])
    created = False
    if viewed.returncode != 0:
        legacy = f"{login}/megabrain"
        legacy_view = run(["gh", "repo", "view", legacy, "--json", "visibility"])
        if legacy_view.returncode == 0:
            try:
                legacy_details = json.loads(legacy_view.stdout)
            except json.JSONDecodeError:
                legacy_details = {}
            if str(legacy_details.get("visibility", "")).upper() == "PRIVATE":
                return legacy, github_remote_for(legacy), False
        created_result = run(
            [
                "gh", "repo", "create", repository, "--private", "--disable-issues", "--disable-wiki",
                "--description", "Private local-first Markdown memory for trusted AI agents",
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
    return str(path.resolve()) if path.exists() or value.startswith((".", "/")) else value.rstrip("/")


def clone_path(home: Path, harness: str) -> Path:
    return home / ".megabrain" / "clones" / harness


def is_empty_repository(root: Path) -> bool:
    return run(["git", "rev-parse", "--verify", "HEAD"], root).returncode != 0


def remote_has_main(root: Path) -> bool:
    listed = run(["git", "ls-remote", "origin"], root)
    if listed.returncode != 0:
        raise BootstrapError("SYNC_FAILED", "The private MegaBrain repository could not be reached.")
    references = {
        line.split("\t", 1)[1]
        for line in listed.stdout.splitlines()
        if "\t" in line
    }
    if "refs/heads/main" in references:
        return True
    if references:
        raise BootstrapError("SYNC_FAILED", "The private MegaBrain repository does not have the expected main branch.")
    return False


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
    if run(["git", "push", "-u", "origin", "main"], root).returncode != 0:
        raise BootstrapError("SEED_PUSH_FAILED", "The initial private brain could not be synchronized to GitHub.")


def assert_clean(root: Path) -> None:
    status = run(["git", "status", "--porcelain", "--untracked-files=all"], root)
    if status.returncode != 0:
        raise BootstrapError("CLONE_INVALID", "The managed MegaBrain clone is not a Git repository.")
    if any(line.strip() for line in status.stdout.splitlines()):
        raise BootstrapError("CLONE_DIRTY", "The managed MegaBrain clone has unexpected local edits.")


def rewrite_legacy_unpushed_seed(root: Path) -> bool:
    workflow = root / LEGACY_SEED_WORKFLOW_PATH
    if not os.path.lexists(workflow):
        return False

    seed = source_skill_root() / "seed"
    expected_files = {
        source.relative_to(seed).as_posix(): source.read_bytes()
        for source in seed.rglob("*")
        if source.is_file() and not source.is_symlink()
    }
    expected_paths = set(expected_files) | {LEGACY_SEED_WORKFLOW_PATH.as_posix()}
    commit_count = run(["git", "rev-list", "--count", "HEAD"], root)
    branch = run(["git", "symbolic-ref", "--short", "HEAD"], root)
    subject = run(["git", "show", "-s", "--format=%s", "HEAD"], root)
    listed = run(["git", "ls-tree", "-r", "--name-only", "HEAD"], root)
    tracked_paths = set(listed.stdout.splitlines()) if listed.returncode == 0 else set()
    try:
        workflow_matches = (
            workflow.is_file()
            and not workflow.is_symlink()
            and workflow.read_bytes() == LEGACY_SEED_WORKFLOW
        )
        seed_matches = all(
            (root / relative).is_file()
            and not (root / relative).is_symlink()
            and (root / relative).read_bytes() == content
            for relative, content in expected_files.items()
        )
    except OSError:
        workflow_matches = False
        seed_matches = False
    recognized = (
        workflow_matches
        and commit_count.returncode == 0
        and commit_count.stdout.strip() == "1"
        and branch.returncode == 0
        and branch.stdout.strip() == "main"
        and subject.returncode == 0
        and subject.stdout.strip() == "feat: initialize private MegaBrain"
        and tracked_paths == expected_paths
        and seed_matches
    )
    if not recognized:
        raise BootstrapError(
            "LEGACY_SEED_UNSAFE",
            "The interrupted MegaBrain seed contains unexpected committed changes and was not modified.",
        )

    removed = run(["git", "rm", "--", LEGACY_SEED_WORKFLOW_PATH.as_posix()], root)
    amended = run(
        ["git", "-c", "commit.gpgsign=false", "commit", "--amend", "--no-edit", "--no-verify"],
        root,
    ) if removed.returncode == 0 else removed
    if removed.returncode != 0 or amended.returncode != 0:
        run(["git", "restore", "--staged", "--worktree", "--", LEGACY_SEED_WORKFLOW_PATH.as_posix()], root)
        raise BootstrapError("SEED_MIGRATION_FAILED", "The interrupted MegaBrain seed could not be safely upgraded.")
    for directory in (workflow.parent, workflow.parent.parent):
        try:
            directory.rmdir()
        except OSError:
            pass
    return True


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
        if run(["git", "clone", remote, str(root)], root.parent).returncode != 0:
            raise BootstrapError("CLONE_FAILED", "The private MegaBrain repository could not be cloned.")
        created = True
    if is_empty_repository(root):
        seed_repository(root)
    elif not remote_has_main(root):
        rewrite_legacy_unpushed_seed(root)
        if not push_with_retry(root):
            raise BootstrapError("SYNC_FAILED", "The private MegaBrain repository could not be synchronized.")
    else:
        fetched = run(["git", "fetch", "origin", "main"], root)
        rebased = run(["git", "rebase", "origin/main"], root) if fetched.returncode == 0 else fetched
        if rebased.returncode != 0:
            run(["git", "rebase", "--abort"], root)
            raise BootstrapError("SYNC_FAILED", "The private MegaBrain repository could not be synchronized.")
    return root, created


def ensure_brain_manifest(root: Path) -> bool:
    path = root / "megabrain.json"
    if path.exists():
        brain_metadata(root)
        return False
    source = source_skill_root() / "seed" / "megabrain.json"
    if not source.exists():
        raise BootstrapError("SEED_MISSING", "The MegaBrain compatibility manifest is missing.")
    shutil.copy2(source, path)
    run(["git", "add", "--", "megabrain.json"], root)
    if run(["git", "commit", "-m", "chore: add brain compatibility manifest"], root).returncode != 0:
        path.unlink(missing_ok=True)
        raise BootstrapError("MIGRATION_FAILED", "The private brain compatibility manifest could not be committed.")
    if not push_with_retry(root):
        print("MegaBrain: compatibility manifest added locally; synchronization is pending.", file=sys.stderr)
    return True


def record_text(meta: dict[str, object], body: str) -> str:
    return f"<!-- megabrain-meta\n{json.dumps(meta, indent=2, sort_keys=True)}\n-->\n\n{body.strip()}\n"


def load_or_create_identity(root: Path, harness: str, display_name: str) -> tuple[dict[str, str], bool]:
    path = root / ".megabrain" / "local.json"
    if path.exists():
        identity = load_json(path, "IDENTITY_INVALID", "The local agent identity is invalid.")
        if identity.get("harness") != harness:
            raise BootstrapError("IDENTITY_MISMATCH", "This clone belongs to another agent harness.")
        return {key: str(value) for key, value in identity.items()}, False
    identity = {"id": str(uuid.uuid4()), "harness": harness, "display_name": display_name, "created_at": utc_now()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return identity, True


def push_with_retry(root: Path) -> bool:
    for _ in range(3):
        if run(["git", "push", "origin", "HEAD:main"], root).returncode == 0:
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
        "schema": "megabrain.agent.v1", "id": identity["id"], "harness": identity["harness"],
        "display_name": identity["display_name"], "created_at": identity["created_at"],
    }
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        record_text(meta, f"# Agent: {identity['display_name']}\n\nProvenance identity for a trusted {identity['harness']} environment."),
        encoding="utf-8",
    )
    run(["git", "add", "--", str(registry.relative_to(root))], root)
    if run(["git", "commit", "-m", f"agent: register {identity['harness']} {identity['id']}"], root).returncode != 0:
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

Use relevant current memories privately. Surface every relevant conflicting claim and ask for clarification. Continue from local state during outages and mention staleness only when material. Show any returned `runtime_update.notice` once.

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


def install_skill(home: Path, harness: str, target: Path) -> Path:
    link_rel, _ = HARNESS_PATHS[harness]
    link = home / link_rel
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        resolved = link.resolve()
        managed = runtime_base(home) in resolved.parents or (home / ".megabrain" / "clones") in resolved.parents
        if resolved != target.resolve() and not managed:
            raise BootstrapError("SKILL_PATH_OCCUPIED", "The agent's MegaBrain skill path belongs to another installation.")
        if resolved != target.resolve():
            link.unlink()
            link.symlink_to(target)
        return link
    if link.exists():
        raise BootstrapError("SKILL_PATH_OCCUPIED", "The agent's MegaBrain skill path is occupied by another installation.")
    link.symlink_to(target)
    return link


def helper_command(skill: Path, root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return run(
        [sys.executable, str(skill / "scripts" / "megabrain.py"), *arguments],
        root,
        env={"MEGABRAIN_ROOT": str(root)},
    )


def validate_clone(root: Path, skill: Path) -> dict[str, Any]:
    validated = helper_command(skill, root, "validate")
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
    runtime, runtime_meta, distribution = install_runtime(home, args.distribution)
    command = install_command(home)
    runtime_skill = runtime / "skill" / "megabrain"
    repository, remote, repository_created = resolve_repository(home, args.repository, args.allow_local_remote)
    root, clone_created = ensure_clone(home, harness, remote)
    manifest_created = ensure_brain_manifest(root)
    validation = validate_clone(root, runtime_skill)
    brain = brain_metadata(root)
    if brain["protocol_version"] > runtime_meta["protocol_version"]:
        raise BootstrapError("PROTOCOL_UPDATE_REQUIRED", "This brain requires a newer MegaBrain runtime.")
    display_name = args.display_name or f"{harness.title()} on {os.uname().nodename}"
    identity, identity_created = load_or_create_identity(root, harness, display_name)
    configure_git(root, f"MegaBrain {identity['display_name']}", identity["id"])
    registered = register_agent(root, identity)
    link = install_skill(home, harness, runtime_skill)
    _, instructions_rel = HARNESS_PATHS[harness]
    replace_block(home / instructions_rel, instruction_block(link / "scripts" / "megabrain.py"))
    config = load_config(home)
    if not config:
        config = {"schema": CONFIG_SCHEMA, "created_at": utc_now(), "clones": {}}
    config.update({"repository": repository, "remote": remote})
    config.setdefault("clones", {})[harness] = str(root)
    config["runtime"] = {
        "version": runtime_meta["version"], "protocol_version": runtime_meta["protocol_version"],
        "source": distribution, "automatic_updates": runtime_meta["automatic_updates"] == "compatible",
    }
    save_config(home, config)
    validation = validate_clone(root, runtime_skill)
    browser: dict[str, Any] | None = None
    if not args.no_open:
        browsed = helper_command(runtime_skill, root, "browse")
        if browsed.stdout.strip():
            try:
                browser = json.loads(browsed.stdout)
            except json.JSONDecodeError:
                browser = {"generated": False, "opened": False}
    return {
        "ok": True, "message": SETUP_READY_MESSAGE, "harness": harness, "repository": repository,
        "repository_created": repository_created, "clone_created": clone_created,
        "manifest_created": manifest_created,
        "identity_created": identity_created, "registered": registered, "runtime_version": runtime_meta["version"],
        "agent_id": identity["id"], "counts": validation["counts"], "browser": browser, "command": command,
    }


def configured_root(home: Path, harness: str) -> tuple[dict[str, Any], Path, Path]:
    config = load_config(home, required=True)
    root_value = config.get("clones", {}).get(harness)
    if not root_value:
        raise BootstrapError("SETUP_REQUIRED", "MegaBrain is not connected to this agent.")
    root = Path(str(root_value)).expanduser().resolve()
    skill = current_runtime(home) / "skill" / "megabrain"
    validate_runtime_release(current_runtime(home))
    return config, root, skill


def release_versions(remote: str) -> list[tuple[tuple[int, int, int], str]]:
    listed = run(["git", "ls-remote", "--tags", "--refs", remote, "v*"])
    if listed.returncode != 0:
        raise BootstrapError("UPDATE_UNAVAILABLE", "MegaBrain could not reach the official release repository.")
    found: dict[tuple[int, int, int], str] = {}
    for line in listed.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        tag = parts[1].removeprefix("refs/tags/")
        version = semantic_version(tag)
        if version:
            found[version] = tag
    return sorted((version, found[version]) for version in found)


def checkout_release(remote: str, tag: str, destination: Path) -> tuple[Path, str]:
    cloned = run(["git", "clone", "--quiet", "--depth", "1", "--branch", tag, remote, str(destination)])
    if cloned.returncode != 0:
        raise BootstrapError("UPDATE_DOWNLOAD_FAILED", "MegaBrain could not download the selected release.")
    commit = run(["git", "rev-parse", "HEAD"], destination)
    if commit.returncode != 0:
        raise BootstrapError("UPDATE_INVALID", "The downloaded MegaBrain release is invalid.")
    return destination / "skill" / "megabrain", commit.stdout.strip()


def require_brain_compatibility(config: dict[str, Any], version: str, metadata: dict[str, Any]) -> None:
    selected = semantic_version(version)
    if selected is None:
        raise BootstrapError("RUNTIME_VERSION_MISMATCH", "The selected MegaBrain runtime version is invalid.")
    roots = [Path(str(path)).expanduser().resolve() for path in config.get("clones", {}).values()]
    for root in roots:
        brain = brain_metadata(root)
        if brain["protocol_version"] > metadata["protocol_version"]:
            raise BootstrapError("PROTOCOL_UPDATE_REQUIRED", "The selected runtime cannot read this brain protocol.")
        minimum = semantic_version(str(brain["minimum_runtime"]))
        if minimum is None or selected < minimum:
            raise BootstrapError(
                "RUNTIME_TOO_OLD",
                "The selected runtime is older than a connected brain's minimum safe runtime.",
            )


def update_runtime(args: argparse.Namespace) -> dict[str, Any]:
    require_command("git")
    home = args.home.expanduser().resolve()
    config = load_config(home, required=True)
    runtime_config = config.get("runtime")
    if not isinstance(runtime_config, dict):
        raise BootstrapError("RUNTIME_MIGRATION_REQUIRED", "Run MegaBrain setup once to migrate this installation.")
    current_version = str(runtime_config.get("version", ""))
    current_tuple = semantic_version(current_version)
    if current_tuple is None:
        raise BootstrapError("CONFIG_INVALID", "The installed MegaBrain version is invalid.")
    state_path = update_state_path(home)
    state = load_json(state_path, "UPDATE_STATE_INVALID", "MegaBrain update state is invalid.") if state_path.exists() else {}
    checked = parse_timestamp(str(state.get("checked_at", "")))
    if args.automatic and state.get("status") != "offline" and checked and datetime.now(timezone.utc) - checked < UPDATE_INTERVAL:
        return {"ok": True, "checked": False, "updated": False, "reason": "check_not_due", "current_version": current_version}
    remote = str(runtime_config.get("source") or OFFICIAL_DISTRIBUTION)
    try:
        versions = release_versions(remote)
    except BootstrapError as error:
        if args.automatic:
            save_private_json(state_path, {"checked_at": utc_now(), "status": "offline", "current_version": current_version})
        if args.automatic or args.check:
            return {"ok": True, "checked": True, "updated": False, "stale": True, "reason": error.code.lower(), "current_version": current_version}
        raise
    requested = semantic_version(args.version) if args.version else None
    if args.version and requested is None:
        raise BootstrapError("INVALID_VERSION", "MegaBrain versions use major.minor.patch format.")
    latest_stable_tuple = versions[-1][0] if versions else current_tuple
    latest_stable = ".".join(map(str, latest_stable_tuple))
    selected = requested or latest_stable_tuple
    tag_by_version = dict(versions)
    if selected not in tag_by_version:
        if selected == current_tuple and runtime_release(home, current_version).exists():
            metadata = validate_runtime_release(runtime_release(home, current_version), current_version)
            selected_tag = f"v{current_version}"
        else:
            raise BootstrapError("VERSION_NOT_FOUND", "The requested MegaBrain release does not exist.")
    else:
        selected_tag = tag_by_version[selected]
        metadata = None
    target_version = ".".join(map(str, selected))
    if args.check:
        return {
            "ok": True, "checked": True, "updated": False,
            "update_available": selected != current_tuple,
            "current_version": current_version, "latest_version": target_version,
            "latest_stable_version": latest_stable,
        }
    approved = bool(getattr(args, "approve_major", False))
    if selected[0] != current_tuple[0] and not approved:
        save_private_json(state_path, {"checked_at": utc_now(), "status": "approval_required", "current_version": current_version, "latest_version": target_version})
        return {
            "ok": True, "checked": True, "updated": False, "approval_required": True,
            "approval_reason": "major_version", "current_version": current_version,
            "latest_version": target_version, "latest_stable_version": latest_stable,
        }
    commit = None
    target = runtime_release(home, target_version)
    if not target.exists():
        with tempfile.TemporaryDirectory(prefix="megabrain-update-") as temporary:
            checkout, commit = checkout_release(remote, selected_tag, Path(temporary) / "release")
            downloaded = runtime_metadata(checkout)
            if str(downloaded["version"]) != target_version:
                raise BootstrapError("RUNTIME_VERSION_MISMATCH", "The release metadata does not match its version tag.")
            metadata = copy_runtime_release(checkout, target)
    metadata = metadata or validate_runtime_release(target, target_version)
    require_brain_compatibility(config, target_version, metadata)
    current_metadata = validate_runtime_release(current_runtime(home), current_version)
    if metadata["protocol_version"] != current_metadata["protocol_version"] and not approved:
        save_private_json(state_path, {"checked_at": utc_now(), "status": "approval_required", "current_version": current_version, "latest_version": target_version})
        return {
            "ok": True, "checked": True, "updated": False, "approval_required": True,
            "approval_reason": "protocol_version", "current_version": current_version,
            "latest_version": target_version, "latest_stable_version": latest_stable,
        }
    activate_runtime(home, target_version)
    runtime_config.update({"version": target_version, "protocol_version": metadata["protocol_version"]})
    config["runtime"] = runtime_config
    save_config(home, config)
    save_private_json(state_path, {"checked_at": utc_now(), "status": "updated", "current_version": target_version, "release_commit": commit})
    changed = target_version != current_version
    return {
        "ok": True, "checked": True, "updated": changed, "previous_version": current_version,
        "current_version": target_version, "latest_version": target_version,
        "latest_stable_version": latest_stable, "release_commit": commit,
        "notice": f"MegaBrain: updated to v{target_version}." if changed else None,
    }


def git_count(repository: Path, *arguments: str) -> int | None:
    counted = run(["git", "rev-list", "--count", *arguments], repository)
    if counted.returncode != 0:
        return None
    try:
        return int(counted.stdout.strip())
    except ValueError:
        return None


def release_distance(
    repository: Path,
    tag_versions: dict[tuple[int, int, int], str],
    from_version: str,
    to_version: str,
) -> dict[str, Any]:
    start = semantic_version(from_version)
    end = semantic_version(to_version)
    if start is None or end is None or start not in tag_versions or end not in tag_versions or start > end:
        return {"available": False}
    if start == end:
        return {"available": True, "releases": 0, "commits": 0, "merged_prs": 0, "highlights": []}
    revision_range = f"{tag_versions[start]}..{tag_versions[end]}"
    commits = git_count(repository, revision_range)
    if commits is None:
        return {"available": False}
    merged = run(["git", "log", "--merges", "--format=%H%x09%s", revision_range], repository)
    if merged.returncode != 0:
        return {"available": False}
    merged_prs: list[dict[str, Any]] = []
    for line in merged.stdout.splitlines():
        commit, separator, subject = line.partition("\t")
        match = re.match(r"Merge pull request #(\d+)\b", subject)
        if not separator or not match:
            continue
        message = run(["git", "show", "-s", "--format=%B", commit], repository)
        body_lines = [item.strip() for item in message.stdout.splitlines()[1:] if item.strip()]
        merged_prs.append({"number": int(match.group(1)), "title": body_lines[0] if body_lines else subject})
    log = run(["git", "log", "--format=%s", "--no-merges", revision_range], repository)
    commit_titles = [line.strip() for line in log.stdout.splitlines() if line.strip()] if log.returncode == 0 else []
    highlights = [*merged_prs, *({"title": title} for title in commit_titles)][:3]
    return {
        "available": True,
        "releases": sum(1 for version in tag_versions if start < version <= end),
        "commits": commits,
        "merged_prs": len(merged_prs),
        "highlights": highlights,
    }


def open_product_work(remote: str) -> dict[str, Any]:
    repository = github_repository(remote)
    if not repository or not shutil.which("gh"):
        return {"available": False}
    viewed = run(
        [
            "gh", "pr", "list", "--repo", repository, "--state", "open", "--limit", "100",
            "--json", "number,title,isDraft",
        ]
    )
    if viewed.returncode != 0:
        return {"available": False}
    try:
        items = json.loads(viewed.stdout)
    except json.JSONDecodeError:
        return {"available": False}
    if not isinstance(items, list) or not all(
        isinstance(item, dict)
        and isinstance(item.get("number"), int)
        and isinstance(item.get("title"), str)
        and isinstance(item.get("isDraft"), bool)
        for item in items
    ):
        return {"available": False}
    previews = [
        {"number": item["number"], "title": item["title"], "draft": item["isDraft"]}
        for item in items[:3]
    ]
    drafts = sum(1 for item in items if item["isDraft"])
    return {
        "available": True, "total": len(items), "draft": drafts,
        "ready": len(items) - drafts, "previews": previews,
    }


def repository_glance(
    remote: str,
    previous_version: str,
    active_version: str,
    latest_stable_version: str,
) -> dict[str, Any]:
    glance: dict[str, Any] = {
        "available": False,
        "included": {"available": False},
        "stable_gap": {"available": False},
        "development": {"available": False},
        "open_work": open_product_work(remote),
    }
    with tempfile.TemporaryDirectory(prefix="megabrain-glance-") as temporary:
        repository = Path(temporary) / "repository"
        cloned = run(["git", "clone", "--quiet", "--no-checkout", remote, str(repository)])
        if cloned.returncode != 0:
            return glance
        listed = run(["git", "tag", "--list", "v*"], repository)
        if listed.returncode != 0:
            return glance
        tag_versions = {
            version: tag
            for tag in listed.stdout.splitlines()
            if (version := semantic_version(tag)) is not None
        }
        previous_tuple = semantic_version(previous_version)
        active_tuple = semantic_version(active_version)
        if previous_tuple is not None and active_tuple is not None and previous_tuple > active_tuple:
            glance["included"] = release_distance(repository, tag_versions, active_version, previous_version)
            glance["included"]["direction"] = "rollback"
        else:
            glance["included"] = release_distance(repository, tag_versions, previous_version, active_version)
            glance["included"]["direction"] = "forward"
        glance["stable_gap"] = release_distance(repository, tag_versions, active_version, latest_stable_version)
        latest = semantic_version(latest_stable_version)
        if latest in tag_versions:
            ahead = git_count(repository, f"{tag_versions[latest]}..origin/main")
            glance["development"] = {"available": ahead is not None, "commits_ahead": ahead}
        glance["available"] = all(
            section.get("available", False)
            for section in (glance["included"], glance["stable_gap"], glance["development"])
        )
    return glance


def status(args: argparse.Namespace) -> dict[str, Any]:
    home = args.home.expanduser().resolve()
    harness = detect_harness(args.harness)
    config, root, skill = configured_root(home, harness)
    validation = validate_clone(root, skill)
    synced = helper_command(skill, root, "sync")
    try:
        sync_result = json.loads(synced.stdout)
    except json.JSONDecodeError:
        sync_result = {"synced": False, "stale": True, "reason": "status_unavailable"}
    update_args = argparse.Namespace(home=home, automatic=False, check=True, version=None)
    update = update_runtime(update_args)
    identity_exists = (root / ".megabrain" / "local.json").exists()
    return {
        "ok": True, "ready": identity_exists and validation["ok"], "harness": harness,
        "repository": config.get("repository"), "counts": validation["counts"], "sync": sync_result,
        "runtime": update, "message": "MegaBrain is ready." if identity_exists else "MegaBrain needs repair.",
    }


def open_brain(args: argparse.Namespace) -> dict[str, Any]:
    home = args.home.expanduser().resolve()
    harness = detect_harness(args.harness)
    _, root, skill = configured_root(home, harness)
    command = ["browse"] + (["--no-open"] if args.no_open else [])
    browsed = helper_command(skill, root, *command)
    output = browsed.stdout if browsed.stdout.strip() else browsed.stderr
    try:
        result = json.loads(output)
    except json.JSONDecodeError as error:
        raise BootstrapError("BROWSER_FAILED", "MegaBrain could not open the local browser.") from error
    if browsed.returncode != 0:
        raise BootstrapError("BROWSER_FAILED", "MegaBrain could not open the local browser.")
    host = result.get("host") or os.uname().nodename
    result["message"] = (
        f"MegaBrain opened on {host}."
        if result.get("opened")
        else f"MegaBrain browser is ready on {host}."
    )
    result["device_boundary"] = (
        "The browser is local to the machine running this agent. "
        "Each connected computer or agent has its own local snapshot. "
        'To refresh this one, say "Synchronize and open my MegaBrain."'
    )
    return result


def disconnect(args: argparse.Namespace) -> dict[str, Any]:
    home = args.home.expanduser().resolve()
    harness = detect_harness(args.harness)
    config = load_config(home, required=True)
    root_value = config.get("clones", {}).get(harness)
    root = Path(str(root_value)).expanduser().resolve() if root_value else clone_path(home, harness)
    link_rel, instructions_rel = HARNESS_PATHS[harness]
    link = home / link_rel
    target = current_runtime(home) / "skill" / "megabrain"
    if link.is_symlink() and link.resolve() == target.resolve():
        link.unlink()
    replace_block(home / instructions_rel, None)
    config.setdefault("clones", {}).pop(harness, None)
    save_config(home, config)
    return {
        "ok": True, "message": "MegaBrain is disconnected from this agent.", "harness": harness,
        "local_clone_retained": root.exists(), "runtime_retained": current_runtime(home).exists(),
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
        action.add_argument("--distribution", help=argparse.SUPPRESS)
        action.add_argument("--no-open", action="store_true", help=argparse.SUPPRESS)
    action_help = {
        "status": "Check MegaBrain health and stable update availability",
        "open": "Synchronize, validate, regenerate, and open the private local snapshot",
        "disconnect": "Disconnect this agent while retaining the private repository and clone",
    }
    for command in ("status", "open", "disconnect"):
        action = subparsers.add_parser(command, help=action_help[command])
        action.add_argument("--harness", choices=sorted(HARNESS_PATHS))
        action.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
        if command == "open":
            action.add_argument("--no-open", action="store_true", help=argparse.SUPPRESS)
    update = subparsers.add_parser("update")
    update.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
    update.add_argument("--check", action="store_true")
    update.add_argument("--automatic", action="store_true", help=argparse.SUPPRESS)
    update.add_argument("--version")
    update.add_argument("--approve-major", action="store_true", help=argparse.SUPPRESS)
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
        elif args.command == "update":
            result = update_runtime(args)
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
