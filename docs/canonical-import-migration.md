# Canonical Import And Migration

Import is deliberately review-first:

```text
explicit allowlist inventory
→ safe path and readability checks
→ fingerprint and secret scan
→ inert candidate extraction by prepare-import.py
→ duplicate/conflict comparison
→ ignored staged package
→ owner review of one exact fingerprint
→ immutable batch commit
→ validation and acceptance tests
```

The runtime never crawls an arbitrary tree. `prepare-import.py` is a separate owner-run utility and reads only listed relative files. It rejects traversal, symlink escape, Unicode-confusable paths, control characters, malformed frontmatter, invalid UTF-8, files over 512 KiB, more than 1,000 files, and more than 10 MiB expanded input. Personas, prompts, templates, sessions, journals, `AGENTS.md`, `CLAUDE.md`, `MEMORY.md`, and `USER.md` are classified rather than activated. Secret-like input becomes `sensitive-deferred` without its value entering output.

`import-stage --stdin` accepts at most ten structured candidates and stores a mode-0600 package under ignored `.megabrain/import-staging/`. Every candidate and batch has a fingerprint. Instruction-like long-form evidence may be staged only as an inert resource; it cannot become an active memory.

The owner runs `canonical-local.py approve-import` locally, provides approve/reject for every candidate, repeats the reviewed batch fingerprint, and supplies current source fingerprints. Any changed source or staged byte invalidates approval. A same-host lock serializes concurrent attempts; the immutable import manifest makes retries idempotent.

Coverage entries distinguish discovered, scanned, candidate-extracted, intentionally skipped, instruction/persona/template/transcript exclusion, sensitive/deferred, canonical-not-scanned, imported, duplicate, conflict, rejected, and acceptance-tested states. `coverage` reports totals and unresolved items.

## Protocol Migration

Existing protocol-1 memories and IDs remain valid. No automatic schema change occurs. Before migration, run `megabrain status` and `megabrain doctor`, inventory every connected writer, and confirm each writer runs a protocol-2-capable runtime. Create and verify an owner-local plaintext bundle backup before approval. Stop incompatible writers rather than allowing them to recreate protocol-1 state.

The owner-local `migrate-v1` command creates the protocol-2 layout and changes only `megabrain.json` in one commit. Failure restores the prior manifest and removes new markers. After migration, run status plus synthetic context/search checks through each supported authorized harness. Runtimes older than the manifest's `minimum_runtime` are rejected for writes. `rollback-head` accepts only the latest canonical/policy commit and creates a Git revert; it never resets or rewrites history. Rehearse that rollback on synthetic data before a personal migration.

### Upgrading a v1 consumer

Use only these steps. Run owner-local commands through the agent's skill link, for example `~/.claude/skills/megabrain/scripts/`. The link tells the command which managed clone to use, so `MEGABRAIN_ROOT` is not needed.

1. `python3 ~/.<harness>/skills/megabrain/scripts/bootstrap.py update` (an agent may run this).
2. `megabrain status`. Each capability that is not ready carries a `remediation` with the exact `command` and an `owner_local_terminal_required` flag.
3. In your own interactive terminal, not an agent shell escape: `python3 ~/.<harness>/skills/megabrain/scripts/canonical-local.py backup <destination>`, then `canonical-local.py migrate-v1`. These commands ask for typed approval and refuse to run without a real terminal, so an agent cannot approve them for you.
4. `migrate-v1` also applies the identity upgrade that `connect` performs for codex and claude: owner-local context provenance, a `0600` identity file, and the owner private read policy. It reports `owner_policy_created`. Rerunning it changes nothing.
5. `megabrain status` should now report `private_recall` ready.

Troubleshooting:

- `CLONE_NOT_RESOLVED`: MegaBrain is set up, but the command was run from a path outside a skill link (for example the resolved release folder). Rerun it through `~/.<harness>/skills/megabrain/scripts/`. `SETUP_REQUIRED` now means no clone is configured at all.
- `trusted_context_missing` or `owner_policy_missing` on `private_recall`: run the `remediation` command, `bootstrap.py connect --harness <harness>`. Consumers who migrated with an earlier 2.x runtime should run it once. A policy that was revoked on purpose is never recreated.

Migration sources remain usable until fingerprint checks, retrieval acceptance, backup inventory, and rollback rehearsal pass. Final source freeze, writer shutdown, archive retirement, reviewed backfill, and consumer cutover require separate approval. Backfill records source coverage, deduplicates by existing identity or fingerprint, excludes secret-like material, and does not treat retrieval ranking as proof of coverage.
