# MegaBrain Product

## Promise

Teach one connected agent; every connected agent can use the same current context without a server or database.

## Protocol 2 Draft

MegaBrain combines a versioned local runtime with a replicated private canonical Markdown repository for one person. It stores bounded memories plus immutable documents, runbooks, project state, decisions, findings, and archive evidence. Review-first migration and scoped policies prevent literal consolidation from becoming automatic source crawling or importance-based disclosure.

## Principles

1. The person owns the brain; agents are replaceable replicas and contributors.
2. Local reads continue when GitHub is unavailable.
3. Git is synchronization and audit history, not a database server.
4. Immutable entries make concurrent writes safe and correction history visible.
5. Context is task-specific rather than a memory dump.
6. Natural conversation is the primary interface.
7. Imports extract durable knowledge instead of copying archives.
8. Secrets never enter the brain.
9. Repository creation, clone paths, harness detection, identity registration, and validation are invisible onboarding details.
10. The public product repository is the software source of truth; a user's private repository is their personal-data source of truth.
11. Runtime updates are versioned, validated, reversible, and never modify memory records.
12. Long-form resources have stable URIs, immutable revisions, explicit authority, provenance, review state, sensitivity, and freshness.
13. Indexes and always-on caches are disposable projections of committed canonical data.
14. Sensitive synchronized assets remain unavailable until their separate security track passes review.

## V1 Acceptance

One copied repository setup message must teach an unfamiliar agent how to install and connect MegaBrain without requiring a clone path or harness choice. Three independent Codex, Claude, and Hermes clones must share a synthetic fact, preserve concurrent writes, observe a correction, surface conflicts, respect a tombstone, recover from offline writes, and ingest a synthetic source idempotently. The initial repository contains no personal memories. Compatible runtime updates and rollback must leave memory files untouched.

## Non-goals And Gates

Protocol 2 does not provide a hosted service, authoritative database, autonomous crawler, raw transcript store, real secret synchronization, hard regulatory erasure, or automatic migration/cutover from previous brains. It does not make runtime filtering a substitute for filesystem isolation. Release, real-source migration, consumer enablement, source retirement, and high-assurance security language remain explicit approval gates.
