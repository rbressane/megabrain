# Install MegaBrain

This document is written for the agent performing installation. Keep repository paths, harness flags, and Git operations out of the normal user experience.

## Agent Entry Point

If a user gives you this repository and asks to install it, including with a short request such as `Install this: https://github.com/rbressane/megabrain`, that is the complete setup request. Follow this document end to end. Do not ask the user to identify their agent environment, choose a repository, select a clone path, or translate these instructions into commands.

## Safety

1. Use only the official `https://github.com/rbressane/megabrain` repository.
2. Inspect the selected release and this document before executing its code.
3. Install a stable `vMAJOR.MINOR.PATCH` tag, never a moving branch.
4. Ask the user before starting GitHub authentication or creating the private repository.
5. Never request, copy, store, or print tokens, passwords, private keys, cookies, or recovery codes during normal Brain installation. Vault setup is a separate owner-local flow and writes recovery material once to an explicit protected file.

## Procedure

1. Verify Python 3.10+, Git, and the GitHub CLI are available.
2. Determine the latest stable MegaBrain release tag from the official repository.
3. Clone that tag into a temporary directory.
4. Run `python3 install.py setup`. Supply `--harness codex`, `--harness claude`, or `--harness hermes` only if automatic detection needs help.
5. If setup returns `GITHUB_AUTH_REQUIRED`, obtain the user's approval, complete `gh auth login`, and retry.
6. Do not select a repository or clone path for the user. Setup creates or finds the authenticated account's private `megabrain-data` repository automatically.
7. Remove the temporary source checkout after setup succeeds.
8. Report only `MegaBrain is ready.` unless the user asks for technical details.

Setup installs the selected runtime under `~/.megabrain/runtime/releases/`, activates it through `~/.megabrain/runtime/current`, creates an isolated private brain clone for the active agent, registers provenance, installs the skill link, validates synchronization, and opens the local brain browser.

## Optional Vault Setup

Do not enable Vault unless the user asks. `vault setup` installs the pinned `PyNaCl>=1.5,<2` dependency into `~/.megabrain/runtime/vault-deps/python-X.Y/` with `pip --no-input --no-cache-dir`; the Brain runtime and users who never enable Vault remain dependency-free. Installation failure removes partial dependency state and does not create the Vault.

Passphrases, recovery keys, item values, attachments, and plaintext reveal are accepted only by the human-only local TTY control plane, never by agent JSON, chat, command-line arguments, environment variables, URL parameters, or shell history literals. The TTY uses no-echo prompts. Setup creates the Vault outside the managed clone, requires an explicit non-existing recovery destination, writes it mode `0600`, returns only a safe receipt, and remains pending until the owner separately confirms it was saved. Do not automate that confirmation.

The owner launches it directly with `python3 ~/.megabrain/runtime/current/skill/megabrain/scripts/vault-local.py <action>`. Begin with `setup`, save the recovery file outside the managed clone, and then run `confirm` separately. The active agent must not run or answer the interactive prompts on the owner's behalf.

The model-facing command surface supports safe status, doctor, lock, and signed masked-metadata requests. Other actions return `LOCAL_ACTION_REQUIRED` without reflecting rejected input.

Private delivery is a separate opt-in after Vault setup. It requires a reviewed harness integration, owner-local key unlock, an exact paired owner destination, a per-resource policy, and fresh one-shot approval for every request. Installing MegaBrain alone does not pair a harness or enable delivery. Credentials remain non-revealable and can be used only through an owner-granted exact adapter capability; this release includes only a synthetic no-network reference adapter.

When updating a schema-1 Vault to a 1.2 runtime, first create and retain an encrypted `.mbvault` export through the owner-local control plane. The first schema-2 open performs one SQLite transaction without rewriting encrypted items or attachments. A failure rolls back; downgrade after a successful migration is unsupported. Follow [docs/vault-attestation.md](docs/vault-attestation.md) for the migration and rollback boundary.

Vault is supported on macOS and Linux because the broker uses a Unix-domain socket. This release does not support Windows, TCP, HTTP, LAN, or remote-agent Vault access.

## Existing Users

Running setup again is idempotent. If the authenticated GitHub account already has a configured brain or legacy private `megabrain` repository, setup connects the active agent to it. Installations made before versioned runtimes are migrated by adding compatibility metadata and repointing the managed skill link; existing memories and Git history are preserved.

For an installed agent:

- `bootstrap.py update --check` checks the official stable releases.
- `bootstrap.py update` installs the latest compatible release.
- `bootstrap.py update --version 1.0.0` activates a specific compatible release for recovery.
- `bootstrap.py disconnect --harness <harness>` removes only MegaBrain-managed links and instructions. It retains the runtime, private repository, and local brain clone.
