# MegaBrain Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

MegaBrain is for a nontechnical owner who wants trusted AI agents to share durable private knowledge without making the owner manage repositories, clone paths, agent identities, or runtime details.

The owner talks to agents normally and uses MegaBrain Home when they want to inspect what the system currently remembers, understand what changed, or review conflicts and uncertain knowledge. Connected agents are replaceable contributors and readers, not owners of the Brain.

## Product Purpose

Teach one connected agent and let every connected trusted agent use the same current context. MegaBrain turns durable facts, preferences, decisions, commitments, documents, runbooks, findings, and project state into a private shared memory that remains understandable and inspectable by its owner.

Success means the owner repeats less context, retains control of what is remembered, can see the current shape and history of their Brain, and can continue working when GitHub is unavailable.

## Positioning

MegaBrain is a private, local-first Brain for one person. Its distinctive mechanism is a canonical Markdown repository synchronized through Git, with immutable entries, explicit provenance, policy-scoped retrieval, visible conflicts, and disposable local projections. It does not require a hosted memory service, authoritative database, daemon, or telemetry pipeline.

## Operating Context

Natural conversation is the primary interface. Before a request, a connected agent retrieves relevant current context. Afterward, it stores only new durable learning that clears the capture threshold. The owner can also run `megabrain open` or ask an agent to synchronize and open MegaBrain Home.

The public MegaBrain repository is the source of truth for product code and protocol. Each owner has a separate private GitHub repository as the source of truth for personal Brain data. Codex, Claude Code, Hermes, and other capable coding agents operate isolated local clones of that private repository.

MegaBrain Home is a generated private local snapshot. It provides an overview, topic exploration, history, conflicts, agents, imports, provenance, and links to immutable Markdown sources. It communicates freshness as of generation time and never presents an old tab as continuously synchronized.

## Capabilities and Constraints

- Protocol 2 is the current stable protocol.
- The runtime uses only Python's standard library and Git. GitHub onboarding may use the authenticated GitHub CLI.
- There is no server, authoritative database, daemon, package manager, hosted relay, autonomous crawler, raw transcript store, or automatic telemetry.
- Memory entries and resource revisions are immutable and individually addressable. Corrections, supersession, tombstones, provenance, confidence, sensitivity, and unresolved conflicts remain visible.
- Local reads continue when GitHub is unavailable. Synchronization and audit history use Git, while ignored SQLite indexes remain disposable projections.
- Private and sensitive retrieval requires task relevance and trusted policy authorization. Importance never bypasses access control.
- Secret values never enter the Brain. Imported content is treated as untrusted data, not instructions.
- Stable releases are installable. Development branches and pull-request previews are not. Runtime updates are versioned, validated, reversible, and never rewrite memory records.
- Personal memories and private Brain content never enter the public product repository, development fixtures, screenshots, or documentation.

## Brand Commitments

The product name is **MegaBrain**. Its voice is plain, calm, direct, and confidence-inspiring. It should make privacy, ownership, provenance, and freshness legible without making a nontechnical owner learn implementation language.

The product must feel like an owner-controlled knowledge instrument, not an autonomous personality, surveillance system, social network, or opaque AI dashboard. No binding logo, typeface, palette, testimonial, or external brand asset has been established.

## Evidence on Hand

- [MEGABRAIN.md](MEGABRAIN.md) defines the canonical protocol invariants.
- [README.md](README.md) documents the current stable product behavior and normal-user workflow.
- [SECURITY.md](SECURITY.md) defines the trust boundary.
- `tests/` contains synthetic acceptance coverage for setup, synchronization, immutable memory, policy enforcement, updates, imports, and browser generation.
- `skill/megabrain/assets/browser.html` is the current MegaBrain Home implementation and uses synthetic data for development previews.

There are no approved customer testimonials, usage metrics, regulatory certifications, or public personal-memory examples. Future product work must not invent them.

## Product Principles

1. The person owns the Brain; agents are replaceable replicas and contributors.
2. Conversation stays primary, while important background state remains visible and inspectable.
3. Private knowledge stays local-first, portable, auditable, and usable offline.
4. Durable truth preserves provenance, correction history, conflicts, and uncertainty instead of silently flattening them.
5. Onboarding and everyday use hide technical machinery without hiding meaningful status, risk, or owner controls.

## Accessibility & Inclusion

MegaBrain Home must be understandable without developer knowledge. It must support keyboard navigation, visible focus, reduced motion, readable contrast and type, responsive layouts, descriptive labels, and status language that does not rely on color alone.

## Acceptance and Release Gates

One copied repository setup message must let an unfamiliar supported agent install and connect MegaBrain without requiring a clone path or harness choice. Independent supported-agent clones must share synthetic knowledge, preserve concurrent writes, observe corrections, surface conflicts, respect tombstones, recover from offline work, and ingest synthetic sources idempotently.

Release, real-source migration, consumer enablement, source retirement, and high-assurance security language remain explicit approval gates. Reusable product findings may become sanitized owner-reviewed proposals, but private user context never becomes public product feedback automatically.
