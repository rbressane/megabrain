# V0 Threat Model

## Assets And Trust

Assets are private facts, provenance, resource locators, agent credentials, and invitation tokens. The local administrator and database operator are trusted. Connected agents are only trusted within explicit scopes; prompts and remote content are untrusted.

## Threats And Controls

- **Brainlink theft:** short expiry, 256-bit randomness, single atomic claim, stored hash, pending status, explicit approval.
- **Credential theft and agent impersonation:** one-time issuance, hash-only storage, authorization-header transport, constant-time comparison, no credential export, immediate revocation checks. V0 lacks rotation and automated anomaly detection.
- **Revoked-agent reuse:** status is read on every request; no cached authorization decision survives revocation.
- **Overbroad scopes:** requested and approved scopes are separate; the administrator explicitly selects from a fixed list; sensitivity scopes are applied before serialization.
- **Prompt injection:** the server accepts structured operations and deterministic tasks, never executes instructions from facts, never performs server-side LLM extraction, and returns only scoped context. A compromised authorized agent can still misuse data it is allowed to read.
- **Accidental secret submission:** defensive pattern rejection and a separate `secret-reference` path. Pattern matching is incomplete and is not a data-loss-prevention guarantee.
- **Sensitive logs:** request bodies are not application-logged; audits contain IDs, classifications, outcomes, and reason codes rather than values. Infrastructure access logs and crash systems still require deployment review.
- **Database compromise:** hash-only credentials reduce immediate credential disclosure, but facts and locators are plaintext in PostgreSQL. V0 relies on database access controls, backups, and deployment-level encryption.
- **Malicious connected agent:** least privilege, auditability, explicit write/correct/forget scopes, and revocation limit damage. V0 has no rate limiter or behavioral detection.
- **Lexical matching limitations:** aliases can miss relevant facts or overmatch terms. Scopes still contain disclosure, but retrieval quality is not semantic and must not be presented as complete.

## Erasure And Recovery

`forget` is a logical tombstone retained for minimal history, not hard deletion or regulatory erasure. Backup deletion, hard-erasure workflow, credential rotation, rate limiting, TLS termination, and disaster recovery are deployment or future work.
