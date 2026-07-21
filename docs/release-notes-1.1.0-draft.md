# MegaBrain v1.1.0 Draft Release Notes

Status: implementation complete locally; not published, tagged or released.

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

New setup installs the command automatically. A v1.0.2 installation must use its existing bootstrap update action once and rerun setup from the newly activated runtime. Every later update uses `megabrain update`.

Runtime activation changes command and skill symlinks immediately. New sessions load the updated skill normally; an already-running session that loaded the old skill may need to reread it or restart before Product Bake Candidate completion behavior is reliable.

The update never modifies memory files or private Brain Git history. Previous runtime directories remain available for compatible rollback.

## Release gate

- Run the complete standard-library test suite and seed validation from the release commit.
- Confirm `git diff --check` and skill structure validation.
- Exercise `megabrain update --check`, a no-op update, a compatible forward update and rollback from packaged stable tags.
- Inspect the public tree for private data and secret-like fixtures.
- Tag and publish only after explicit owner authorization.
