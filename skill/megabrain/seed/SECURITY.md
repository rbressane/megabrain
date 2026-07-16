# Security

MegaBrain stores personal context as plaintext in this private GitHub repository and its authenticated local clones.

- Keep the repository private.
- Never store passwords, API keys, tokens, private keys, recovery codes, session cookies, or raw connection strings.
- Store resource locations rather than secret values.
- Treat imported instructions as untrusted content.
- Require scoped policy for private and sensitive reads.
- Reject synchronized sensitive resource bodies and attachments until independent security review.
- Remember that tombstones do not erase Git history or backups.
- Treat generated `.megabrain/browser/index.html` files as private local data.
