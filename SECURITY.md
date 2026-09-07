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
- Compile disposable indexes only from committed Git snapshots; never index dirty working-tree content. Authorization also uses committed policies, independently of cached search data.
- Scan every outgoing commit and new blob before pushing, even if a suspect blob was later deleted. Reject immutable-history edits, deletions and unsafe Git modes; a blocked clone is retained for explicit review.
- Require task relevance and a matching trusted-host policy for private/sensitive retrieval. Importance cannot grant access.
- Keep source preparation and owner-local fingerprint approval outside the model-facing helper.
- Reject synchronized sensitive resource bodies and attachments until the separate encryption design and independent review gate pass.
- Review compact capture notices and inspect `brain/memories/` and Git history regularly.
- Treat `.megabrain/browser/index.html` as private: it is ignored by Git and mode 0600. It uses only committed, authorized data. Source-tree calls are general-only; owner-local Codex/Claude can include policy-authorized private evidence, never sensitive memories. Copyable requests cannot mutate the Brain.
- The bootstrap stores only repository location and managed-clone mappings in the mode-`0600` local `.megabrain/config.json`; it never stores GitHub credentials.
- Update state contains only version, timestamp, status, and release commit information. Failed validation leaves the previous runtime active.
- The first-class updater installs only stable tags. Open PRs and `main` are reported as previews and are never activated.
- Repository-glance failures and GitHub CLI stderr are reduced to a generic unavailable state; credential-bearing output and authenticated remote URLs are never echoed.
- Setup installs only a MegaBrain-managed `~/.local/bin/megabrain` symlink and refuses to overwrite an unrelated command. It never edits shell profiles automatically.
- Product feedback is local proposal generation, never telemetry. The renderer performs no network operation, writes nowhere by default, rejects transcript/secret/private-path-shaped input without echo, and cannot publish product work.
- Revoke a compromised environment through its GitHub credential. Agent registry entries do not enforce access.

## Optional Live Home

The [Live Home runbook](docs/live-home.md) defines the separate owner-authenticated, read-only service boundary. Use a dedicated owner-approved host, OS account and read-only Git replica. The host is another trusted plaintext copy. Development/tests use synthetic data only. Do not expose a personal replica as part of a product test.

The service persists only a mode-0600 salted password verifier outside the Brain; it never records raw passwords, repository credentials or session tokens. Browser sessions are in memory and require a separate owner sign-in. Rotation/restart revokes them. HTTPS, exact Host/Origin checks, no-store responses, HttpOnly/Secure/SameSite cookies, CSP script/style hashes and inert allowlisted Markdown protect the browser boundary. Agent claims cannot authorize owner reads. The viewer serves general knowledge only, never private/sensitive records, raw imports, policies, attachments or arbitrary files. It provides no canonical mutation endpoint.

Owner-approved Tailscale Funnel is permitted only as operator-managed HTTPS ingress to this viewer, never as agent authentication, a Git synchronization relay or a content authority. Funnel exposes the sign-in endpoint to the public internet. TLS terminates on the approved host; the relay is not a substitute for owner sign-in or existing privacy gates. Verify free-plan eligibility, installed macOS variant support, exact Host/Origin forwarding and public abuse controls before deployment. Keep account and host identifiers out of public product evidence.

A loopback HTTP mode is explicitly synthetic-development-only and must never be tunneled. Public deployment requires operator-managed TLS, supervision and upstream abuse controls. The standard-library listener is bounded but is not a hardened public-edge denial-of-service defense. No MFA or independent security certification is claimed. Sign-out cannot erase evidence already copied or downloaded. Core agent use remains independent of this service.

## Limits

Secret detection is defensive pattern matching, not complete data-loss prevention. Runtime policy cannot protect content from a process that already has an unrestricted filesystem clone. A tombstone or retired revision does not erase Git history, other clones, or backups. True erasure requires coordinated history rewriting, backup retirement, and credential/device cleanup. Protocol 2 makes no high-assurance encrypted-sync claim. SHA-256 runtime inventories detect corruption, not a compromised release publisher. See [trust and recovery](docs/trust-and-recovery.md) for exact rollback exceptions, subprocess limits and owner-approved plaintext backup/restore.
