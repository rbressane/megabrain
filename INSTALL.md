# Install MegaBrain

This document is written for the agent performing installation. Keep repository paths, harness flags, and Git operations out of the normal user experience.

## Agent Entry Point

If a user gives you this repository and asks to install it, including with a short request such as `Install this: https://github.com/rbressane/megabrain`, that is the complete setup request. Follow this document end to end. Do not ask the user to identify their agent environment, choose a repository, select a clone path, or translate these instructions into commands.

## Safety

1. Use only the official `https://github.com/rbressane/megabrain` repository.
2. Inspect the selected release and this document before executing its code.
3. Install a stable `vMAJOR.MINOR.PATCH` tag, never a moving branch.
4. Ask the user before starting GitHub authentication or creating the private repository.
5. Never request, copy, store, or print tokens, passwords, private keys, cookies, or recovery codes.

## Procedure

1. Verify Python 3.10+, Git, and the GitHub CLI are available.
2. Determine the latest stable MegaBrain release tag from the official repository.
3. Clone that tag into a temporary directory.
4. Run `python3 install.py setup`. Supply `--harness codex`, `--harness claude`, or `--harness hermes` only if automatic detection needs help.
5. If setup returns `GITHUB_AUTH_REQUIRED`, obtain the user's approval, complete `gh auth login`, and retry.
6. Do not select a repository or clone path for the user. Setup creates or finds the authenticated account's private `megabrain-data` repository automatically.
7. Remove the temporary source checkout after setup succeeds.
8. Report the compact completion message: `MegaBrain is ready.` followed by `Say "Synchronize and open my MegaBrain" anytime to synchronize, validate, and browse your private Brain locally.`

Setup installs the selected runtime under `~/.megabrain/runtime/releases/`, activates it through `~/.megabrain/runtime/current`, installs `~/.local/bin/megabrain`, creates an isolated private brain clone for the active agent, registers provenance, installs the skill link, validates synchronization, and opens the local brain browser. The command resolves through the managed current-runtime link so later activations switch it atomically. Setup refuses to overwrite an unrelated executable. The browser is a private static snapshot; `Synchronize and open my MegaBrain` is the normal return action that synchronizes, validates, regenerates, and opens it.

If `~/.local/bin` is not on `PATH`, setup returns the exact one-line export required for the current shell. It never edits shell startup files.

## Existing Users

Running setup again is idempotent. If the authenticated GitHub account already has a configured brain or legacy private `megabrain` repository, setup connects the active agent to it. Installations made before versioned runtimes are migrated by adding compatibility metadata and repointing the managed skill link; existing memories and Git history are preserved.

For an installed agent:

- `megabrain update --check` checks the official stable releases without mutation.
- `megabrain update` installs the latest compatible stable release.
- `megabrain update --version 1.0.0` activates a specific compatible release for recovery.
- `megabrain update --json` returns the stable `megabrain.update.v1` output schema.
- `megabrain feedback --stdin` renders a privacy-checked Product Bake Candidate offline and writes nowhere by default.
- `bootstrap.py disconnect --harness <harness>` removes only MegaBrain-managed links and instructions. It retains the runtime, private repository, and local brain clone.

### One-time transition from v1.0.2

Installations made before the first-class command need one bootstrap transition. The installed agent should run the old update action once, then rerun setup from the newly activated runtime:

```bash
python3 "$HOME/.megabrain/runtime/current/skill/megabrain/scripts/bootstrap.py" update
python3 "$HOME/.megabrain/runtime/current/skill/megabrain/scripts/bootstrap.py" setup
```

After that transition, use `megabrain update`. Keep direct bootstrap update access only for this migration and emergency command recovery.
