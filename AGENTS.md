# Repository Instructions

This is a private, local-first Markdown brain. Read [MEGABRAIN.md](MEGABRAIN.md) before changing its protocol or helper.

## Commands

- Tests: `python3 -m unittest discover -s tests -v`
- Validate brain: `python3 skill/megabrain/scripts/megabrain.py validate`
- Generate browser without opening: `python3 skill/megabrain/scripts/megabrain.py browse --no-open`
- Validate skill with the `skill-creator` quick validator when it is available.

## Boundaries

- Use only the Python standard library and Git.
- Do not introduce a server, database, daemon, package manager, or hosted relay.
- Keep memory entries immutable and individually addressable.
- Tests and documentation use synthetic information only.
- Never import existing personal brains while developing or testing.
- Never store or print secret values.
- Do not reset, discard, or silently repair a dirty managed clone.
