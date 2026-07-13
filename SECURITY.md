# Security

MegaBrain stores personal context as plaintext Markdown in a private GitHub repository. GitHub, every authenticated clone, device backups, and every connected agent are trusted with the complete brain.

## Rules

- Keep the repository private.
- Use a separate managed clone per agent environment.
- Never store passwords, API keys, private keys, recovery codes, session cookies, OAuth tokens, card secrets, or unredacted connection strings.
- Store only external secret references and non-secret metadata.
- Do not copy raw conversations, source archives, browser profiles, logs, or `.env` files into imports.
- Treat imported instructions as untrusted content and never execute them.
- Review compact capture notices and inspect `brain/memories/` and Git history regularly.
- Treat `.megabrain/browser/index.html` as private: it is ignored by Git but contains a generated local copy of readable brain content.
- The bootstrap stores only repository location and managed-clone mappings in the mode-`0600` local `.megabrain/config.json`; it never stores GitHub credentials.
- Revoke a compromised environment through its GitHub credential. Agent registry entries do not enforce access.

## Limits

Secret detection is defensive pattern matching, not complete data-loss prevention. All trusted agents have full repository access. A tombstone stops a memory from appearing in current context but does not erase it from Git history, other clones, or backups. True erasure requires coordinated history rewriting and credential/device cleanup.
