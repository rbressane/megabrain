# Repository Instructions

This is the canonical MegaBrain product and protocol repository. Personal memories live only in separate private user repositories. Read [MEGABRAIN.md](MEGABRAIN.md) before changing the protocol, runtime, or helper.

## Source of Truth

Before material project work, read and follow https://markfolio.round6.co/raw/agent-sot-protocol.md. Resolve [.sot.json](.sot.json), read the bound canonical MegaBrain SOT, and never create a duplicate authority.

## Commands

- Tests: `python3 -m unittest discover -s tests -v`
- Validate brain seed: `MEGABRAIN_ROOT=skill/megabrain/seed python3 skill/megabrain/scripts/megabrain.py validate`
- Bootstrap help: `python3 skill/megabrain/scripts/bootstrap.py --help`
- Generate browser without opening: `python3 skill/megabrain/scripts/megabrain.py browse --no-open`
- Retrieval/resource benchmark: `MEGABRAIN_ROOT=skill/megabrain/seed python3 skill/megabrain/scripts/megabrain.py benchmark`
- Validate skill with the `skill-creator` quick validator when it is available.

## Boundaries

- Use only the Python standard library and Git for the core runtime. The narrowly approved Live Home transport below is separate operator infrastructure.
- Do not introduce a server or daemon except for an optional, owner-authenticated, read-only Live Home viewer accessible from normal phone and desktop browsers and its narrowly approved transport below. The core runtime must remain usable without either service, including offline.
- Live Home is a replaceable view of committed Git data, not a new authority. Corrections and forgetting remain agent-driven. Owner authentication must remain separate from agent permissions; this exception does not relax existing privacy or security gates.
- Do not introduce an authoritative database or package manager. Ignored rebuildable SQLite indexes are permitted projections.
- No hosted relay except owner-approved Tailscale Funnel, solely as optional HTTPS ingress to the owner-authenticated, read-only Live Home. Tailscale is operator-managed transport, never a core runtime dependency, agent gateway, Git synchronization relay, or authority. Owner sign-in, general-only browsing and all other privacy/security gates remain required.
- Funnel setup requires an explicitly trusted host/operator, verified free-plan eligibility, no paid subscription, and a documented synthetic deployment acceptance disposition. For the existing 2.5.0 candidate, the owner closed the operator trial and deferred remaining operational checks to usage; record those as deferred, never passed, and do not request another manual acceptance round. Automated regression/CI requirements and authentication/privacy boundaries remain intact. Merge, release publication and personal-replica connection each require explicit authorization. Never expose the synthetic-only `--local-http` mode or publish private host/account details.
- Keep memory entries immutable and individually addressable.
- Tests and documentation use synthetic information only.
- Never import existing personal brains while developing or testing.
- Keep normal-user onboarding conversational; clone paths and harness flags are internal details.
- Never store or print secret values.
- Do not reset, discard, or silently repair a dirty managed clone.
