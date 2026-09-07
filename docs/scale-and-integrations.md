# Scale and integration verification

## Index lifecycle

Memory and resource indexes use independent Git subtree IDs, not the whole HEAD commit, for invalidation. An agent registration, policy revision or unrelated document does not rebuild unchanged knowledge indexes. Access policy is still checked on every operation and is never stored as an index permission.

Cold builds use bounded `git ls-tree` / `git cat-file --batch` reads of the captured commit. This removes temporary per-record filesystem extraction. Rebuilds reuse parsed source rows only when their path and Git blob ID are unchanged. Supersession, current/conflict graphs and postings are still rebuilt; this is incremental source parsing, not a fully incremental search engine.

The ignored databases are private and replace atomically. An interrupted rebuild leaves the prior database intact; a stale database cannot satisfy a new content tree. Corrupt SQLite state rebuilds from committed sources. Dirty records are never indexed. Batches are bounded to 128 MiB of newly read Markdown, with a 64 MiB per-object ceiling; larger corpora fail explicitly rather than consuming unbounded input memory.

Read operations share one committed policy snapshot only while holding the clone operation lock. The next operation rereads current policy, so revocation does not wait for index invalidation. Dirty policy edits cannot grant access.

## Measured baseline

Run `MEGABRAIN_ROOT=skill/megabrain/seed python3 skill/megabrain/scripts/megabrain.py benchmark`.

7 September 2026, macOS arm64, Python 3.14.7, synthetic data:

| Total records | Memories / resources | Cold memory total | Warm memory median | Cold resource index | Warm resource median |
| --- | --- | --- | --- | --- | --- |
| 30 | 15 / 15 | 79.6 ms | 48.6 ms | 33.2 ms | 17.7 ms |
| 1,000 | 500 / 500 | 153.9 ms | 58.0 ms | 126.8 ms | 17.8 ms |
| 10,000 | 5,000 / 5,000 | 1,119.7 ms | 175.5 ms | 637.2 ms | 20.5 ms |

All eight synthetic collection members were returned at every size for both evidence types. These are local helper measurements, not network service-level promises. They exclude live GitHub pull/push latency and do not model every corpus or resource-body size. Pull-before-read and immediate durable-write synchronization remain unchanged. Remote validation, large-body ranking and HTML generation can still dominate other workloads.

## Acceptance coverage

- `tests/test_scale.py`: independent tree reuse, new-blob-only parsing, interrupted rebuild, corrupted database recovery, shared policy evaluation, immediate revocation, dirty-policy denial and subprocess timeout.
- `tests/test_trust.py`: outgoing ancestor secrets, immutable edits/deletions, private/dirty Home projection, runtime completeness, same-clone concurrent writes and backup/restore.
- `tests/test_interface.py`: installed CLI memory lifecycle, project scope, conflict budgets, empty-term queries, help and safe diagnostics.
- `tests/test_knowledge.py`: capture choices, freshness/uncertainty review, proposals, inert Home resources and protected correction history.
- Existing synthetic network tests retain separate-clone concurrency, offline recovery, onboarding, updates, import idempotence and source/citation checks.
- `tests/browser_smoke.py`: real Chrome at four desktop/mobile sizes. See [Home verification](verification/home-owner-workflows.md).

CI runs the standard-library suite on macOS and Linux with Python 3.10, 3.11 and 3.13, plus Chrome smoke on Linux. There is no server or package-manager runtime dependency.

## Agent integration boundary

Installed Codex, Claude and Hermes wrappers exercise synthetic ready → remember → retrieve → proposal → forget → validate journeys. Codex/Claude also exercise owner-local pause/resume. Hermes must reject owner-only capture changes and remains general-only without reviewed provenance.

These tests execute real installed commands, not live model reasoning. They do not prove that an unfamiliar model always follows conversational onboarding or classifies durable knowledge correctly. Separate owner-approved User Zero evaluation remains necessary before real-source cutover; no personal Brain was used here. No mail/calendar/task connector, embedding service, automatic crawler or sensitive Vault consumer is enabled by this release.
