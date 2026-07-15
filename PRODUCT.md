# MegaBrain Product

## Promise

Teach one connected agent; every connected agent can use the same relevant Brain context, while explicitly authorized local agents can use a separate encrypted Vault for sensitive records.

## V1 Product

MegaBrain combines a versioned local runtime with a replicated private Markdown repository for one person. Each trusted agent has its own data clone and stable identity. The universal skill synchronizes through private GitHub, retrieves task-relevant current memory, and captures durable learning during normal conversation. The optional Vault stores encrypted sensitive records and attachments outside Git and grants least-privilege access through an owner-controlled same-host broker.

## Principles

1. The person owns the brain; agents are replaceable replicas and contributors.
2. Local reads continue when GitHub is unavailable.
3. Git is Brain synchronization and audit history, not a database or Vault transport.
4. Immutable entries make concurrent writes safe and correction history visible.
5. Context is task-specific rather than a memory dump.
6. Natural conversation is the primary interface.
7. Imports extract durable knowledge instead of copying archives.
8. Secrets never enter Brain, context packets, imports, Git, or the browser. They enter Vault only through explicit protected operations.
9. Repository creation, clone paths, harness detection, identity registration, and validation are invisible onboarding details.
10. The public product repository is the software source of truth; a user's private repository is their personal-data source of truth.
11. Runtime updates are versioned, validated, reversible, and never modify memory records.
12. Retrieval relevance outranks unrelated importance; a bounded `always` class is the only unconditional context class.
13. Vault is self-owned and works without an external password manager, hosted SaaS, or network listener.
14. Recovery, deletion, revocation, and in-memory limits are described precisely rather than as hard-erasure promises.

## V1 Acceptance

One copied repository setup message must teach an unfamiliar agent how to install and connect MegaBrain without requiring a clone path or harness choice. Three independent Codex, Claude, and Hermes clones must share synthetic normal knowledge while preserving concurrent writes, corrections, conflicts, tombstones, offline recovery, and imports. Retrieval must respect its declared limit, return relevant normal memories despite unrelated core memories, support structured task descriptors and collection expansion, and use a commit-keyed local index.

Vault acceptance uses synthetic data only: passphrase and recovery wrappers unlock the same random master key; per-item keys protect structured records; encrypted attachments authenticate every chunk; signed agent metadata requests enforce scopes, resource classes, freshness, replay defense, revocation, and value-free audits; agent reveal fails closed without independent harness attestation; owner-confirmed reveal and portable clean-home restore are tested; normal Brain use remains available without Vault or PyNaCl.

## User-zero feedback loop

Consumer findings are sanitized into product reproductions with installed version, commit, harness, operating system, observed and expected behavior, measurements, implications, acceptance tests, and post-release verification. Product agents never inspect a real private brain. Changes move through branch, tests, review, release, then consumer retesting marked VERIFIED, PARTIAL, or FAILED.

## Non-goals

This release does not provide a web UI, hosted service, TCP/HTTP Vault access, remote broker, background synchronization requirement, embeddings, raw transcript storage, hard regulatory erasure, or automatic migration from previous brains or Obsidian vaults. External secret-provider adapters remain a future interface seam. Vault's local SQLite database and optional Unix-socket broker are deliberate exceptions to the original Brain-only boundaries.
