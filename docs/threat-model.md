# Threat Model

## Trusted

The brain owner and reviewed owner-local controls are trusted. An unrestricted private clone, its host, and its process space can read plaintext canonical content. Contributing or group-facing agents are not granted unrestricted clones merely because they can submit proposals or receive scoped digests.

## Controls

- Compromised agent or device: revoke its GitHub credential and rotate any exposed external secrets.
- Accidental secrets: input scanning, ignored secret file patterns, pre-commit validation, and value-free rejection reports.
- Prompt injection in imports: sources are data; only durable factual summaries may become memories.
- Source traversal and stale review: an owner-run explicit allowlist rejects symlinks, traversal, confusable paths, malformed metadata, limits violations, and changed post-review fingerprints.
- Context disclosure: private/sensitive retrieval requires relevance plus exact immutable policy and trusted host context; default deny covers group, channel, API, cron, webhook, delegated, background, and unattended contexts.
- Dirty-index poisoning: memory/resource indexes rebuild only from `git archive HEAD` and are ignored by Git.
- Archive tampering: non-sensitive objects are content-addressed and complete-object validated through manifests.
- Concurrent writes: unique immutable files plus fetch/rebase/push retry.
- GitHub outage: local reads and pending local commits.
- Silent corruption: schema validation, Git history, provenance, and conflict surfacing.
- Stale knowledge: explicit correction and tombstone records.
- Compromised product release: stable official tags, local validation before atomic activation, retained prior releases, and no runtime code in the private data clone.
- Repository metadata exposure: update reporting suppresses command stderr, never emits credential-bearing remotes, and treats GitHub PR metadata as optional preview information.
- Command-path collision: setup refuses to replace a `megabrain` executable that it cannot identify as product-managed.
- Product-feedback leakage: agent sanitization plus offline transcript, secret, private-path and local-network URL rejection; no automatic write, network transmission or publication path.

## Accepted Risks

Git hosts and unrestricted clones hold plaintext general/private content. Secret scanning is incomplete. Git history and backups prevent guaranteed erasure. Lexical retrieval can omit relevant knowledge or return extra context within policy. Python cannot guarantee in-memory zeroization. Sensitive synchronized assets are therefore rejected rather than claimed secure; see [sensitive-sync-design.md](sensitive-sync-design.md).
