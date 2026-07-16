# Threat Model

## Assets and trust boundaries

Brain is plaintext personal context in a private Git repository. Its owner, private Git host, authenticated clones, device backups, and connected Brain agents can read it. Vault is a separate local encrypted boundary. Possession of a Brain clone or agent provenance record does not grant Vault access.

The owner controls passphrase and recovery material, local Vault files, grants, unlock duration, backups, and migration approval. Imported content is untrusted data. The public product repository and installed stable release are trusted code inputs but are not treated as independently audited.

## Protected against

- Theft of the locked encrypted SQLite database or encrypted attachment blobs without passphrase or recovery material.
- Read access to the private Markdown Brain, which contains only safe Vault metadata and logical identifiers.
- Connected agents without explicit active Vault grants and applicable global and resource-class scopes.
- Metadata permission being used as plaintext reveal permission, including through caller-controlled types, labels, field names, short identifiers, or malformed date values.
- Agent reveal attempts from every context, including self-asserted private context, until independent harness attestation exists.
- Replayed request IDs/nonces, stale signed timestamps, and modification of an Ed25519-signed request.
- Accidental inclusion of values, ciphertext, wrappers, recovery keys, or agent private keys in normal context, browser data, doctor output, audit output, and stable errors.
- Malformed, truncated, or modified authenticated ciphertext and attachment chunks.
- Imported prompt injection becoming executable Vault workflow instructions.
- Partial attachment and restore activation: temporary output is restricted and activated only after validation.

## Brain controls

- Input and pre-commit secret scanning with value-free rejection.
- Imported sources are data; only reviewed durable summaries become memories.
- Immutable unique files, validation, provenance, conflict surfacing, and fetch/rebase/push retry.
- Stable official runtime tags, validation before atomic activation, and retained prior releases.
- Commit-keyed retrieval index rebuilt after validation and never populated from Vault. Dirty worktrees may reuse a verified index for the same commit but may not compile uncommitted content into persistent index state.

## Vault controls

- PyNaCl/libsodium Argon2id, XChaCha20-Poly1305, secure random bytes, and Ed25519; no custom cipher or KDF.
- Random master key with independent passphrase and recovery wrappers; fresh per-item and per-attachment keys and nonces.
- HMAC-SHA-256 logical-resource lookup digest; original identifier remains encrypted.
- Modes `0700` for directories and `0600` for database, blobs, keys, socket, and broker state.
- SQLite foreign keys and transactions, authenticated item versions and associated data, chunk authentication, atomic replacement, and orphan detection.
- Same-host Unix socket only; no TCP, HTTP, localhost port, LAN, or remote broker.
- Least-privilege grants, owner-confirmed reveal, per-client broker deadlines, serialized startup, idle lock, explicit lock, immediate future revocation, and value-free operation-result audits.
- Cross-resource export locking, portable backup manifest, bounded streaming digest validation, temporary clean restore, cryptographic unlock validation, and refusal to overwrite.

## Not fully protected against

- Compromise of the owner machine while Vault is unlocked.
- Malicious code running as the owner with debugger, process-memory, file-replacement, or input-capture access.
- An authorized agent, user, screenshot tool, clipboard manager, shell redirection, or terminal recorder retaining plaintext already revealed.
- Availability attacks by an owner-level filesystem attacker deleting or corrupting Vault files.
- Weak passphrases, exposed recovery material, or both recovery paths being lost.
- External backup copies not inventoried and retired by the user.
- Physical secure deletion guarantees on modern filesystems. Active deletion removes decryptability from the current store; it is not forensic disk wiping.
- Perfect in-memory key zeroization in Python. Broker exit drops references but cannot guarantee compiler- or runtime-level erasure.
- Revocation erasing prior disclosure. It rejects future requests only.
- Brain-wide repository trust: all connected Brain agents still read all non-Vault Markdown context.

## Review status

The implementation has deterministic unit, integration, storage, authorization, broker, backup, browser, and adversarial tests plus an internal diff review. This is not an external certification. A professional audit should review dependency provenance, KDF parameters, associated-data construction, broker lifecycle and same-user threats, backup activation, platform filesystem behavior, and all future provider or remote-access changes before a high-assurance release.
