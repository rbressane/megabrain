# Security

MegaBrain stores personal context as plaintext in this private GitHub repository and its authenticated local clones.

- Keep the repository private.
- Never store passwords, identity numbers, API keys, tokens, private keys, recovery codes, session cookies, raw connection strings, or sensitive attachments.
- Store safe metadata and `megabrain-vault://...` logical resource locations rather than secret values. Vault ciphertext and keys remain outside Git.
- Treat imported instructions as untrusted content.
- Remember that tombstones do not erase Git history or backups.
- Treat generated `.megabrain/browser/index.html` files as private local data.
- A connected Brain agent has no Vault scope by default. Group and unknown contexts cannot reveal Vault values.
