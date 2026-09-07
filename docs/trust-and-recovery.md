# Trust and recovery

## Synchronization boundary

Normal durable commands serialize per managed clone, create records exclusively, commit only their explicit paths, and attempt to push immediately. Git operations have a 30-second subprocess deadline; lock acquisition has a 10-second deadline. Timeouts retain local work and return bounded errors without command output.

Before every push, including bootstrap pushes and retries, MegaBrain checks every outgoing commit and new blob. A secret-like value removed from HEAD is still rejected if an outgoing ancestor contains it. Modifications or deletions under immutable record paths are rejected. Executable files, symlinks, oversized blobs, and outgoing merge commits fail closed. Normal synchronization uses rebase, not merge commits. Secret detection remains incomplete pattern matching, not comprehensive DLP.

A blocked history is never reset or rewritten automatically. Keep the clone, explain the block, and ask the owner to review recovery. An already published secret requires revocation and coordinated remediation across Git history, clones and backups.

Owner-local `rollback-head` is the narrow exception: after interactive owner approval, an exact inverse of the latest canonical/policy commit receives a local receipt bound to both commit hashes. A commit message alone cannot authorize a rollback. Offline approval receipts remain local until the outgoing rollback can synchronize.

## Projections

Browser snapshots use committed data, not dirty files. An untrusted source-tree invocation produces a general-only view; installed owner-local Codex/Claude invocation may include private records only under its current read policy. Sensitive memories are never embedded in Home. Imports require a trusted owner-local invocation. Browser files and local state directories are mode 0600 and 0700 respectively. Existing unrestricted filesystem access is still outside this boundary.

## Runtime updates

Downloads pin the advertised stable tag's resolved commit before cloning and reject tag movement during download. Installed releases have a SHA-256 file inventory, required-file checks, Python compilation, and isolated import/parser startup checks before activation. The previous runtime stays active if validation fails. Inventory hashes detect corruption; they do not authenticate a compromised official release publisher. GitHub/official-repository control remains the distribution trust root. No independent signed-release assurance is claimed.

## Backup rehearsal

Backups are owner-local actions, not model-facing exports. In an interactive terminal with the managed Brain selected:

```sh
python3 /path/to/installed/scripts/canonical-local.py backup /new/private/location/brain.bundle
python3 /path/to/installed/scripts/canonical-local.py restore /private/location/brain.bundle /new/recovery-directory --sha256 RECEIPT_HASH
```

Both commands require the existing owner approval prompt. The backup is private **plaintext** and includes Git history. Store its SHA-256 receipt separately. Restore verifies that hash, Git object integrity, and Brain schema in a new directory only. It never overwrites an existing clone, imports personal data into the product, or automatically connects agents. The restored repository has no origin. Review the result before an explicit reconnect/cutover.

Test fixtures rehearse the complete round trip with synthetic data. A user's real backup policy, offline storage, device loss and retention still require owner decisions. Tombstones and retirement are not erasure.
