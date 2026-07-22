# MegaBrain 2.0.0 Release Notes

This release separates bounded retrieval from the Vault stack and adds the protocol-2 canonical resource, archive, import, access-policy, and derived-cache model.

It preserves protocol-1 memory IDs and requires an explicit owner-local migration. New resources use stable URIs and immutable revisions; imports are fingerprint-bound and review-first; private/sensitive reads default deny; indexes rebuild from committed Git state; general always-on caches are deterministic and non-authoritative.

The built-in private local browser now reports generation-scoped synchronization, snapshot time, newest-memory freshness, inclusion verification, pending local commit state, and safe stale reasons. Setup teaches `Synchronize and open my MegaBrain` as the single synchronized validation and regeneration action; `Open my MegaBrain` remains equivalent.

Sensitive synchronized bodies and attachments remain unavailable. This release does not migrate real sources, enable consumers, change Hermes memory configuration, or retire any legacy store. User-zero cutover and high-assurance security language still require the approval gates in the review bundle and independent review where stated.

## First-class command

- Setup installs a collision-safe `~/.local/bin/megabrain` command through the atomic current-runtime link.
- `megabrain update` installs the latest compatible stable release.
- `megabrain update --check` is read-only.
- `megabrain update --version X.Y.Z` supports compatible recovery and rollback.
- `megabrain update --json` emits the stable `megabrain.update.v1` schema.
- Human output distinguishes stable release distance, included commits and merge commits, `main` development distance, and open ready/draft PR previews.
- GitHub metadata failure cannot invalidate a successful runtime update.
- Major and protocol-version transitions require explicit owner approval.
- Rollback refuses a runtime below any connected Brain's `minimum_runtime`.

## Product feedback loop

- The shipped skill classifies material reusable user-zero findings before finishing while remaining silent for private, personal, transient, local-only or already-resolved findings.
- `megabrain feedback --stdin` renders the canonical Product Bake Candidate offline and deterministically.
- The renderer rejects unsupported categories, transcript-shaped input, known secret patterns, private paths, local-network URLs and oversized source dumps without echoing rejected values.
- It performs no network operation, writes nowhere by default, refuses output collisions, and has no publication capability.

## Upgrade

New setup installs the command automatically. A v1.0.2 installation must use its existing bootstrap update action once and rerun setup from the newly activated runtime. That major update still requires owner approval, and the protocol-1 to protocol-2 private Brain migration remains the separate explicit owner-local operation documented by the canonical review bundle. Every later runtime update uses `megabrain update`.

Runtime activation changes command and skill symlinks immediately. New sessions load the updated skill normally; an already-running session that loaded the old skill may need to reread it or restart before Product Bake Candidate completion behavior is reliable.

The update never modifies memory files or private Brain Git history. Previous runtime directories remain available for compatible rollback.

## Verification

- The complete 43-test standard-library suite passes from the release candidate.
- Seed validation passes with zero errors and zero warnings.
- The synthetic protocol-2 retrieval/resource benchmark completes successfully.
- `git diff --check`, Python compilation, skill structure validation, and the public-tree secret scan pass.
- Acceptance tests exercise `megabrain update --check`, a no-op update, compatible forward update, major/protocol approval, rollback, metadata degradation, and invalid-release recovery using packaged synthetic tags.
