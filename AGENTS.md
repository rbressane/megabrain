# Repository Instructions

This is the canonical MegaBrain product and protocol repository. Personal memories live only in separate private user repositories. Read [MEGABRAIN.md](MEGABRAIN.md) before changing the protocol, runtime, or helper.

## Commands

- Tests: `python3 -m unittest discover -s tests -v`
- Validate brain seed: `MEGABRAIN_ROOT=skill/megabrain/seed python3 skill/megabrain/scripts/megabrain.py validate`
- Bootstrap help: `python3 skill/megabrain/scripts/bootstrap.py --help`
- Generate browser without opening: `python3 skill/megabrain/scripts/megabrain.py browse --no-open`
- Validate skill with the `skill-creator` quick validator when it is available.

## Boundaries

- Use only the Python standard library and Git.
- Do not introduce a server, database, daemon, package manager, or hosted relay.
- Keep memory entries immutable and individually addressable.
- Tests and documentation use synthetic information only.
- Never import existing personal brains while developing or testing.
- Keep normal-user onboarding conversational; clone paths and harness flags are internal details.
- Never store or print secret values.
- Do not reset, discard, or silently repair a dirty managed clone.
