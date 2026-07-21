# Sensitive Synchronized Assets: Security Gate

Protocol 2 intentionally rejects synchronized `sensitive` bodies and attachments. The local Vault drafts in PRs #9–#11 protect a separate local secret store and attested delivery path; they are not a synchronized canonical document repository.

A future implementation requires, before release claims:

- client-side authenticated encryption with per-resource data keys and device-scoped wrapping keys;
- authenticated metadata with an explicit leakage budget for IDs, sizes, revision cadence, ownership, and access patterns;
- independently authenticated chunks plus a complete-object manifest/root so truncation, reordering, substitution, and mix-and-match fail;
- no plaintext in Git, helper JSON, logs, indexes, environment, argv, temporary files, model context, or crash output;
- recovery, device enrollment/loss, key rotation, revocation, deletion, backup inventory, and retired-device behavior;
- owner-local reveal and reviewed attested delivery boundaries;
- migration/rollback tests and independent external security review.

Until those properties are designed, implemented, and reviewed, use metadata-only resource pointers for sensitive material and migrate non-sensitive canonical documents first. Private Git is access control, not encryption.
