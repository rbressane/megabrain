# Vault Recovery and Backup

## Recovery key

Local TTY setup generates an independent 256-bit recovery key formatted with the `MBRK1-` prefix. It is not a mnemonic and is written exactly once to an explicit recovery file created mode `0600` and never overwritten. Non-interactive JSON and agent tools never receive it. The user must confirm storage in a separate local action before the Vault becomes active.

Keep recovery material separate from the computer and encrypted Vault backup. Anyone with a Vault backup and either the passphrase or recovery key can decrypt it. If both passphrase access and recovery material are lost, MegaBrain cannot recover the master key.

`rotate-recovery` requires an explicit non-existing recovery-file path. It creates that file as mode `0600`, updates the wrapper transactionally, and returns only the file path in ordinary JSON. If wrapper rotation fails, the new file is removed. The old recovery key no longer unlocks the active Vault after success, but an older backup may still contain the old wrapper. Retire old backups deliberately after verifying the new recovery path.

## Passphrase rotation

`rotate-passphrase` authenticates the existing Vault and derives a new Argon2id wrapper. It does not decrypt and rewrite every item or attachment. A failed rotation transaction leaves the old wrapper current.

## Portable backups

Export always requires an explicit non-existing destination and writes a restricted temporary archive before atomic replacement. A cross-resource mutation lock holds the SQLite snapshot and immutable attachment inventory consistent through archive completion. The backup contains only encrypted database state, encrypted blobs, and a digest manifest. Recovery material is never embedded.

At least one recovery exercise should restore into a clean second home using the backup and independent recovery key, reveal a selected synthetic verification field in a private authorized flow, and run `vault doctor`. A backup that cannot be restored has not been verified.

Restore accepts only the uncompressed portable format, enforces file-count, per-entry, manifest, and total expanded-size ceilings, and streams entries into a restricted temporary directory. It validates all hashes, checks schema/suite and Brain/Vault identity, unlocks cryptographically, authenticates every active item, compares active attachment inventory, then atomically activates. Existing Vault directories are never overwritten. Wrong passphrase or recovery material and corrupted archives leave no partial Vault.

## Deletion and backup retirement

Deleting an active item does not modify already exported backups. Maintain an inventory of backup locations and dates. After sensitive deletion or key rotation, create and verify a current backup, retire obsolete copies according to the storage provider's capabilities, and record only safe retirement metadata. MegaBrain cannot assert deletion from offline media, snapshots, cloud version history, or copies outside its control.
