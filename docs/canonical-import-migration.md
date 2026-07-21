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

Existing protocol-1 memories and IDs remain valid. No automatic schema change occurs. The owner-local `migrate-v1` command creates the protocol-2 layout and changes only `megabrain.json` in one commit. Failure restores the prior manifest and removes new markers. `rollback-head` accepts only the latest canonical/policy commit and creates a Git revert; it never resets or rewrites history.

Migration sources remain usable until fingerprint checks, retrieval acceptance, backup inventory, and rollback rehearsal pass. Final source freeze, writer shutdown, archive retirement, and consumer cutover require separate approval.
