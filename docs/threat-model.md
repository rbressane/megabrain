# Threat Model

## Trusted

The brain owner, private GitHub repository, authenticated clones, and all connected agents are trusted to read and write all knowledge.

## Controls

- Compromised agent or device: revoke its GitHub credential and rotate any exposed external secrets.
- Accidental secrets: input scanning, ignored secret file patterns, pre-commit validation, and value-free rejection reports.
- Prompt injection in imports: sources are data; only durable factual summaries may become memories.
- Concurrent writes: unique immutable files plus fetch/rebase/push retry.
- GitHub outage: local reads and pending local commits.
- Silent corruption: schema validation, Git history, provenance, and conflict surfacing.
- Stale knowledge: explicit correction and tombstone records.

## Accepted Risks

GitHub and all clones hold plaintext personal context. Access is repository-wide. Secret scanning is incomplete. Git history and backups prevent guaranteed erasure. Lexical retrieval can omit relevant knowledge or return extra context.
