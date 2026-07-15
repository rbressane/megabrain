# MegaBrain Vault

Vault is the optional local encrypted store for values and documents that must never enter Brain Markdown, Git, context packets, import manifests, logs, or the local browser. The built-in provider requires no external password manager or hosted service.

## Location and lifecycle

Vault setup assigns or reuses the stable `brain_id` from `megabrain.json` and creates:

```text
~/.megabrain/vaults/<brain-id>/
  vault.sqlite3
  attachments/
  runtime/
  audit/
```

Directories are `0700` and state files are `0600`. This directory is outside every managed Git clone. A user who never runs `vault setup` has no Vault database and does not need PyNaCl.

Setup receives a passphrase on standard input, generates an independent recovery key, and returns or writes that key exactly once. The database remains `pending_confirmation` until a second setup call confirms recovery was saved. Setup never silently regenerates material.

## Commands

All content-bearing commands accept one JSON object on standard input. Never put passphrases, recovery keys, values, or private fields in command-line arguments or environment variables.

- `vault setup`: create the pending Vault or confirm recovery material.
- `vault status`: report existence, ready/locked state, suite, schema, and safe counts.
- `vault unlock`: authenticate through passphrase or recovery key and start the same-host broker for a 5–3600 second idle timeout.
- `vault lock`: stop the broker and discard its in-process master-key reference.
- `vault put`: create or correct a structured encrypted item. Rewrites use a new item key and nonce.
- `vault metadata`: send a signed broker request for safe masked metadata.
- `vault reveal`: perform an owner-authenticated, explicitly confirmed reveal of selected fields to a private output context. Agent broker reveal fails closed until the harness can provide independently verifiable privacy attestation.
- `vault attach`: add an encrypted file or authenticate and extract it to an explicit non-existing destination.
- `vault export`: create an explicit non-existing `.mbvault` backup destination.
- `vault restore`: validate and activate a matching-brain backup only when no Vault exists.
- `vault grant` / `vault revoke`: manage a specific agent's public key, scopes, and resource classes.
- `vault rotate-passphrase`: rewrap the master key without re-encrypting items.
- `vault rotate-recovery`: replace the recovery wrapper and write the new key once to an explicit non-existing mode-`0600` file; ordinary command JSON never contains it.
- `vault delete`: destroy active item and attachment key wrappers and remove active blobs.
- `vault audit`: return value-free allowed and denied events.
- `vault doctor`: check dependency, permissions, suite, schema, SQLite integrity, grants, broker state, and orphaned blobs without revealing values.

Machine-readable failures use stable codes and do not reflect rejected secrets. Human agents should translate the flow conversationally instead of asking users to construct JSON.

## Structured records and masking

An encrypted item contains schema, logical identifier, type, label, fields, and timestamps. Item type and field names must match the versioned allow-list; arbitrary caller-defined schema names are rejected. Logical identifiers are provider-independent, for example:

```text
identity://synthetic-subject/passport/example/current
megabrain-vault://identity/synthetic-subject/passport/example/current
```

The database indexes only a keyed digest. Returned labels are protected. Identity document numbers of five or more characters show only the final two characters behind at least eight bullets; shorter values are fully protected. Credential and recovery fields display `[protected]`; only strictly valid `YYYY-MM-DD` date metadata may be displayed. Masking is type- and field-specific rather than a universal “last four” rule.

## Attachments

Attachments are limited to 100 MiB and encrypted in 1 MiB authenticated chunks. Filename, MIME type, size, and chunk count are encrypted. MegaBrain writes a restricted temporary ciphertext file, fsyncs it, coordinates the database transaction and atomic rename under the same mutation lock used by export, and deletes failed temporary or final output. Extraction authenticates every chunk and the complete ciphertext digest before reporting success, writes only to an explicit destination, refuses overwrite, and never opens the result automatically.

## Active deletion

Deletion immediately marks the item unavailable, nulls the active payload and wrapped item key, nulls attachment key material, removes local encrypted blobs, and records a value-free event. This gives loss of active decryptability in the current Vault. It does not promise physical disk erasure or deletion of external `.mbvault` files. Users must inventory and retire backups separately.

## Migration readiness

Migration from Obsidian, an external password manager, or an older store is never automatic. The reviewed flow is: inventory sources and coverage; classify safe memory, sensitive metadata, and sensitive value; present masked candidates; obtain approval; write values to Vault and only logical metadata to Brain; verify retrieval and clean restore; mark old pointers transitional or superseded; then retire old stores only after zero dangling references. Development and acceptance use synthetic sources only.

## Limits

Remote access, TCP, HTTP, LAN access, automatic attachment opening, hard secure erasure, perfect Python memory zeroization, revocation of prior disclosure, external-provider adapters, and automatic legacy migration are not supported in this release.
