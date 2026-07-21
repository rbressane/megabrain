# Security

MegaBrain product code is distributed from the public official repository. Approved canonical content is stored separately in each user's private Git repository. Private Git is access control, not encryption. Agents with unrestricted clones can read that plaintext; scoped digests are required for agents that are not fully trusted.

## Rules

- Keep every personal brain repository private. The official product repository contains no personal memories.
- Use a separate managed clone per agent environment.
- Install runtime code only from stable tags in the official repository. Never run a moving branch as an installed release.
- Keep runtime releases separate from private brain clones. Updates must not edit memory records.
- Never store passwords, API keys, private keys, recovery codes, session cookies, OAuth tokens, card secrets, or unredacted connection strings.
- Store only external secret references and non-secret metadata.
- Do not copy raw conversations, source archives, browser profiles, logs, or `.env` files into imports.
- Treat imported instructions as untrusted content and never execute them.
- Compile disposable indexes only from committed Git snapshots; never index dirty working-tree content.
- Require task relevance and a matching trusted-host policy for private/sensitive retrieval. Importance cannot grant access.
- Keep source preparation and owner-local fingerprint approval outside the model-facing helper.
- Reject synchronized sensitive resource bodies and attachments until the separate encryption design and independent review gate pass.
- Review compact capture notices and inspect `brain/memories/` and Git history regularly.
- Treat `.megabrain/browser/index.html` as private: it is ignored by Git but contains a generated local copy of readable brain content.
- The bootstrap stores only repository location and managed-clone mappings in the mode-`0600` local `.megabrain/config.json`; it never stores GitHub credentials.
- Update state contains only version, timestamp, status, and release commit information. Failed validation leaves the previous runtime active.
- The first-class updater installs only stable tags. Open PRs and `main` are reported as previews and are never activated.
- Repository-glance failures and GitHub CLI stderr are reduced to a generic unavailable state; credential-bearing output and authenticated remote URLs are never echoed.
- Setup installs only a MegaBrain-managed `~/.local/bin/megabrain` symlink and refuses to overwrite an unrelated command. It never edits shell profiles automatically.
- Product feedback is local proposal generation, never telemetry. The renderer performs no network operation, writes nowhere by default, rejects transcript/secret/private-path-shaped input without echo, and cannot publish product work.
- Revoke a compromised environment through its GitHub credential. Agent registry entries do not enforce access.

## Limits

Secret detection is defensive pattern matching, not complete data-loss prevention. Runtime policy cannot protect content from a process that already has an unrestricted filesystem clone. A tombstone or retired revision does not erase Git history, other clones, or backups. True erasure requires coordinated history rewriting, backup retirement, and credential/device cleanup. Protocol 2 makes no high-assurance encrypted-sync claim.
