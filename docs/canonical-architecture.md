# Canonical Repository Architecture

Protocol 2 makes a user's private MegaBrain the canonical repository for durable memories, long-form resources, runbooks, decisions, findings, project state, and approved archive evidence. Live transactional systems remain authoritative for their current native state. External knowledge stores are migration sources or disposable views after an explicit cutover.

## Layers

1. **Bounded retrieval** uses disposable SQLite indexes compiled only from `git archive HEAD`. `core` affects tie-breaking only; it never bypasses relevance or `--limit`. At most three reviewed `always` invariants enter every result. Bounded collection and conflict expansions are reported explicitly.
2. **Canonical resources** use stable `megabrain://resource/<uuid>` URIs and immutable revisions under `brain/resources/`. Current state is derived from supersession and retirement links.
3. **Review-first migration** separates source preparation from runtime approval. `prepare-import.py` reads only an owner allowlist. The normal helper stages structured candidates outside Git. `canonical-local.py` imports one exact fingerprint after owner review.
4. **Scoped access** stores immutable policy revisions under `brain/policies/`. Private and sensitive reads default deny and require trusted host context; model payload fields cannot grant access.
5. **Derived projections** export a bounded general-sensitivity `always` cache without write-back. Watcher state remains outside both source and destination repositories.
6. **Sensitive synchronized assets** remain fail-closed. Protocol 2 does not claim encrypted multi-device document synchronization; see [sensitive-sync-design.md](sensitive-sync-design.md).

## Repository Layout

```text
brain/
  memories/YYYY/MM/
  resources/{contexts,projects,runbooks,decisions,findings,documents,archives}/<resource-id>/<revision-id>.md
  attachments/manifests/<manifest-id>.json
  attachments/objects/sha256/<prefix>/<digest>
  imports/<batch-id>.md
  policies/<agent-id>/<revision-id>.json
  agents/<agent-id>.md
```

Ignored `.megabrain/` state contains only disposable indexes, staged candidate packages, locks, value-free policy audits, and generated browser output. It is never canonical.

## Authority Boundary

MegaBrain is canonical for durable reusable knowledge and archived evidence. Product repositories remain canonical for executable code and code-coupled docs; task systems for current assignments; mail/calendars for current messages/events; infrastructure for live runtime state; and an externally reviewed encrypted system for secret values. MegaBrain records may point to those systems or preserve approved snapshots without claiming to replace their live state.

## Documentation Index

- [Resource and attachment format](canonical-resource-format.md)
- [Import, coverage, and migration](canonical-import-migration.md)
- [Authority and scoped access](canonical-access-policy.md)
- [Archive and retention](canonical-archive-retention.md)
- [Recovery and rollback](canonical-recovery-rollback.md)
- [Sensitive synchronization gate](sensitive-sync-design.md)
- [User-zero acceptance](canonical-user-zero-acceptance.md)
- [Requirements-to-tests matrix](canonical-requirements-to-tests.md)
- [MegaBrain 2.0.0 release notes](release-notes-2.0.0.md)
- [MegaBrain 2.0.1 private-retrieval repair draft](release-notes-2.0.1-draft.md)
