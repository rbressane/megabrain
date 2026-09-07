# MegaBrain 2.3.0

A compatible protocol-2 reliability and owner-workflow release. No Brain migration or private-history rewrite is required.

## 1. Trust repair

- Outgoing commits and blobs are checked before pushing, including secrets removed from HEAD. Immutable edits/deletions and unsafe Git modes fail closed; exact owner-reviewed operational rollback remains a narrowly bound exception.
- Clone locks, exclusive records, atomic private files and bounded Git subprocesses protect routine operations without silently repairing dirty clones.
- Home uses committed, policy-filtered snapshots with owner-only permissions and never embeds sensitive memories.
- Complete runtime files, isolated startup, commit pinning and installed SHA-256 inventories are checked before activation. Inventories are corruption detection, not signed publisher authentication.
- Owner-approved plaintext Git-bundle backup/restore rehearses recovery into a new, disconnected destination.

## 2. One command interface

The installed `megabrain` command exposes existing helper operations, including search, context, remember/correct/forget, resources, diagnostics and synchronization. Project scope applies to memories as well as resources. Empty-term queries are safe; bounded results expose truncation and incomplete conflicts.

## 3. Daily owner workflows

Graph-first Home adds resources, project filtering, review reminders, capture state and honest agent status. Correction, forgetting and resource review prepare copyable owner requests only. CLI review/handoff and per-owner-local-agent capture controls use the same runtime. Uncertainty, dates and normalized duplicate summaries remain evidence, never automatic truth changes.

## 4. Scale and integrations

Indexes use separate content-tree keys and incremental source parsing through bounded committed-object batches. Unchanged knowledge survives unrelated commits without rebuilding. A single read shares committed policy evaluation, but no authorization cache survives the operation. CI covers macOS/Linux across three Python versions, plus real Chrome smoke and synthetic installed Codex/Claude/Hermes journeys.

The 10,000-record mixed synthetic benchmark measured 1.12 seconds cold memory retrieval and 176 ms warm median locally, excluding live GitHub latency. See [measurement and limits](scale-and-integrations.md).

## Verification and limits

The release candidate has 85 standard-library tests, seed validation and real-browser checks at 1440×1000, 1920×800, 390×844 and 430×1100. Exact release CI is recorded on GitHub. UI verification is scoped, not a full accessibility certification.

Private Git is not encryption. Secret detection is incomplete pattern matching. Runtime policies cannot sandbox an agent with unrestricted plaintext filesystem access. Hermes private retrieval, Vault encryption and attested delivery remain gated behind their independent review tracks. Installed-wrapper tests are not a substitute for User Zero model/workflow acceptance. No personal Brain data was read or migrated.

## Update

```sh
megabrain update --check
megabrain update
```

Start a new agent session or reread the installed skill to load new workflow instructions. Existing owner policies, captures and private history remain intact. See [command interface](command-interface.md), [owner workflows](owner-workflows.md), and [trust and recovery](trust-and-recovery.md).
