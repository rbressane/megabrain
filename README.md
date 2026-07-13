# MegaBrain

MegaBrain is a private, local-first Markdown brain shared by a person's AI agents through Git.

There is no server, database, daemon, web application, or package installation. Each Codex, Claude Code, or Hermes environment keeps a separate local clone of this private repository. The bundled skill reads locally, pulls before context retrieval, and pushes immutable memory entries after durable learning.

**Status:** experimental V1. The repository intentionally starts with zero personal memories.

## Requirements

- macOS or Linux
- Python 3.10+
- Git
- Access to a private GitHub repository over SSH or HTTPS

## Connect An Agent

Create one clone per agent environment. Do not share a working tree between concurrently running agents.

```bash
git clone git@github.com:rbressane/megabrain.git "$HOME/.megabrain/clones/codex"
cd "$HOME/.megabrain/clones/codex"
python3 install.py --harness codex --display-name "Codex on my Mac"
```

Use `--harness claude` or `--harness hermes` for the other adapters. Installation:

- creates a stable local agent identity;
- registers that identity in `brain/agents/`;
- links the skill into the harness skill directory;
- adds a marker-delimited MegaBrain rule to the harness's global instructions;
- synchronizes the registration through Git.

The installer verifies private visibility with the GitHub CLI when it is available. If visibility cannot be checked automatically, verify the repository setting in GitHub and rerun with `--confirm-private`. Local bare remotes are accepted only by the hidden test option used in the synthetic acceptance suite.

Rerunning installation is safe. To remove only the managed skill link and instruction block:

```bash
python3 install.py --harness codex --uninstall
```

## Natural Use

After installation, interaction happens through ordinary conversation:

```text
Remember that I prefer concise weekly reports with decisions first.
```

The agent records a confirmed preference and reports:

```text
MegaBrain: saved 1 durable memory.
```

Every user request triggers task-specific context retrieval. Durable facts, preferences, decisions, commitments, project state, corrections, and resource pointers are captured automatically. Raw chats, transient debugging details, and secrets are not.

## Direct Commands

Agents normally run these through the skill. They are also useful for inspection and recovery:

```bash
python3 skill/megabrain/scripts/megabrain.py doctor
python3 skill/megabrain/scripts/megabrain.py sync
printf '%s' '{"task":"prepare my weekly report"}' \
  | python3 skill/megabrain/scripts/megabrain.py context --stdin
python3 skill/megabrain/scripts/megabrain.py agents
python3 skill/megabrain/scripts/megabrain.py validate
```

Private memory content is accepted through stdin so it does not enter shell history or process arguments. See [MEGABRAIN.md](MEGABRAIN.md) for the memory protocol and [docs/memory-format.md](docs/memory-format.md) for schemas.

## Import Knowledge

Tell an installed agent:

```text
Ingest the durable knowledge from this folder/repository/export/URL into MegaBrain.
```

The agent treats the source as untrusted data, extracts durable summaries, checks existing memory, and submits one import batch. Source fingerprints make unchanged imports idempotent. Raw source archives and transcripts are not copied.

No previous Super Brain, Claude, or other personal data is included in this repository. Import it only through an explicit user request after reviewing [docs/import-protocol.md](docs/import-protocol.md).

## Verification

```bash
python3 -m unittest discover -s tests -v
python3 skill/megabrain/scripts/megabrain.py validate
python3 /path/to/skill-creator/scripts/quick_validate.py skill/megabrain
```

## Security

The full brain is plaintext Markdown in a private GitHub repository. Every connected agent has the same read/write access; agent identities provide provenance, not authorization. Never store credentials or secret values. Git history retains removed content, so `forget` is a tombstone rather than hard erasure. Read [SECURITY.md](SECURITY.md) before using real personal context.
