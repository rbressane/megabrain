# Vault Format

Vault schema versioning is independent from the Brain protocol. Version 1 uses SQLite as a ciphertext container, not as encryption.

## Cryptographic suite

Suite identifier: `pynacl-argon2id-xchacha20poly1305-ed25519-v1`.

- PyNaCl/libsodium Argon2id interactive parameters derive a 256-bit passphrase key from a random 16-byte salt.
- A random 256-bit master key is wrapped independently by the passphrase key and a random 256-bit recovery key.
- XChaCha20-Poly1305 uses 256-bit keys, 192-bit random nonces, and a 128-bit authenticator.
- Every item has a fresh random 256-bit data key. Every attachment has a fresh random 256-bit file key.
- HMAC-SHA-256 under the unlocked master key indexes normalized logical identifiers.
- Agent requests use Ed25519 keys. SHA-256 fingerprints identify registered public keys.

No nonce is reused intentionally. Rewriting an item generates a new item key and fresh payload and wrapper nonces. Associated data binds item schema, opaque item ID, keyed resource digest, item version, and encryption purpose. Attachment associated data binds format, attachment ID, item ID, chunk index, total chunks, and purpose.

## SQLite entities

- `vault_header`: schema and suite, random Vault and stable Brain IDs, creation/status, explicit Argon2id parameters and salt, passphrase wrapper, and recovery wrapper.
- `items`: opaque ID, keyed resource digest, encrypted payload, wrapped item key, nonces, version, timestamps, and deletion marker.
- `attachments`: opaque attachment/item IDs, encrypted metadata, wrapped file key, nonces, opaque blob name, ciphertext digest, timestamp, and deletion marker.
- `agent_grants`: agent ID, Ed25519 public key/fingerprint, explicit scopes and classes, active/revoked state, timestamps, and policy version.
- `audit_events`: random ID, timestamp, agent ID, action, keyed resource reference, outcome, reason code, and request ID. It contains no value or free-form sensitive purpose.
- `broker_requests`: used request IDs, nonces, timestamps, and agent IDs for replay defense.

Foreign keys are enabled. Schema creation is transactional. The implementation refuses unsupported schema or suite values.

## Encrypted item JSON

The authenticated payload uses `megabrain.vault-item.v1` and contains logical ID, record type, label, fields, and creation/update timestamps. Version 1 allow-lists the `passport`, `identity`, `identity-document`, `credential`, `recovery-code`, `health-record`, and `financial-account` types and a fixed safe field-name vocabulary for each. Unknown types and field names are rejected so caller-controlled schema text cannot escape through metadata. Field names are encrypted with values. The original logical ID never appears as a database index.

An attacker with only locked database bytes can infer the suite, KDF cost, Vault/Brain random IDs, creation and update timing, ciphertext sizes, approximate row and attachment counts, deleted state, agent IDs and grants, and value-free audit activity. The attacker cannot directly read logical resource names, labels, field names, values, filenames, MIME types, or attachment plaintext.

## Attachment blob

The blob starts with `MBVAT1\n`, a big-endian chunk count, then records of 24-byte nonce, 4-byte ciphertext length, and authenticated ciphertext. The database authenticates encrypted metadata and stores the SHA-256 digest of all chunk records. Files larger than 100 MiB are rejected.

## Backup

`megabrain.vault-backup.v1` is a ZIP container with `manifest.json`, a consistent encrypted `vault.sqlite3` snapshot, and active encrypted blobs under `attachments/`. The manifest contains only Vault/Brain IDs, format version, creation time, and SHA-256 inventory. It contains no recovery key or plaintext item data. ZIP path traversal, missing/extra entries, digest mismatch, wrong Brain ID, wrong unlock material, corrupt items, and inconsistent blob inventory are rejected before atomic activation.
