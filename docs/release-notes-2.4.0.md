# MegaBrain 2.4.0

Daily automatic updates during ordinary use, with real owner controls. Protocol remains 2; no Brain migration is required.

## Changes

- Context, search, resource reads, review and Home share one elapsed-24-hour check per OS user/device. No daemon or scheduled job.
- Automatic checks are nonblocking against another updater. Git subprocesses share a ten-second foreground budget; failures back off from five minutes to six hours without blocking local reads.
- `megabrain updates status|enable|disable|pin|unpin` controls local preferences. Reconnect preserves them. Enabling preserves a pin; unpinning preserves a disabled setting.
- Explicit rollback automatically pins its target. A pin prevents later activation until removed. Rollback requires a pin-aware runtime; older releases require separately reviewed legacy recovery.
- Every command pins modules, metadata and assets to its starting release. The new runtime applies to subsequent commands. Managed durable writes exclude activation while they run.
- Atomic, private switch receipts recover interrupted link/configuration changes to the previous runtime. Existing releases and Brain history remain intact.
- Successful activation gives a concise notice. Changed skill instructions request a reload or fresh session. The same incompatible release does not ask for approval every day.
- Explicit `update --check` bypasses the throttle without changing runtime or schedule. Major/protocol transitions still require approval. Invalid releases never activate.

## Adoption

Existing 2.3 installations can use their existing context-triggered updater or run `megabrain update` once. Broader triggers begin after 2.4 activates. Reload the MegaBrain skill or start a fresh session for the new controls. No personal Brain import, rewrite, or reconnect is needed for this release.

See [runtime updates](runtime-updates.md) for exact scheduling, rollback limits and failure behavior.

## Verification and boundaries

Synthetic tests cover every eligible installed read, all three harnesses, concurrent checks, offline/backoff behavior, pin persistence, invalid and incompatible releases, unchanged Brain data, durable-write exclusion, interrupted activation and old/new asset isolation. The full standard-library suite, seed validation and real Chrome Home checks are release gates. Exact-commit matrix CI is recorded on GitHub.

Runtime inventory hashes detect corruption, not a compromised publisher. Private Git is not encryption. Vault, sensitive synchronization, attested delivery and Hermes private provenance remain independently gated. Synthetic installed-command acceptance is not certification of live model behavior or real-network latency.
