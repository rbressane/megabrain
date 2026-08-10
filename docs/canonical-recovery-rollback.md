# Canonical Recovery And Rollback

Canonical records remain ordinary immutable Git data. Rebuild both SQLite indexes by deleting ignored `.megabrain/*-index.sqlite3`; the next clean read reconstructs them from `git archive HEAD`. Staged packages and policy audits are local operational state, not authority.

Protocol migration is one commit. If validation or acceptance fails, keep source stores writable and revert only that migration commit. `canonical-local.py rollback-head` refuses arbitrary history and accepts only the current canonical/policy commit. It uses `git revert`, validates the result, and pushes through the normal synchronization path. It never resets a dirty clone.

An import rollback likewise reverts the latest batch commit, restoring the previous canonical view while retaining auditable Git history. If later canonical commits exist, perform a reviewed targeted revert rather than automatic rollback. Source material must not be frozen or retired until rollback has been rehearsed and backup inventory is complete.

The owner-read repair has two independent rollback boundaries. Runtime rollback can reactivate the preceding compatible runtime without changing the Brain. Authorization rollback creates an immutable revocation revision through the owner-local policy control; setup will not recreate that policy afterward. Do not delete policy files or reset history. The ignored local provenance marker may remain because it grants nothing without a matching current policy.
