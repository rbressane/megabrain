# MegaBrain Product

## Promise

Teach one connected agent; every connected agent can use the same current context without a server or database.

## V1 Product

MegaBrain is a local-first replicated Markdown repository for one person. Each trusted agent has its own clone and stable identity. A universal skill synchronizes through private GitHub, retrieves task-relevant current memory, and captures durable learning during normal conversation.

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

## V1 Acceptance

One conversational setup action must create or connect the private repository and active agent without requiring a clone path or harness choice. Three independent Codex, Claude, and Hermes clones must share a synthetic fact, preserve concurrent writes, observe a correction, surface conflicts, respect a tombstone, recover from offline writes, and ingest a synthetic source idempotently. The initial repository contains no personal memories.

## Non-goals

V1 does not provide a web UI, hosted service, database, background synchronization daemon, embeddings, semantic search, access tiers, raw transcript storage, secret management, hard regulatory erasure, or automatic migration from previous brains.
