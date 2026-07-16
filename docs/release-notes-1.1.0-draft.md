# MegaBrain 1.1.0 Draft Release Notes

Version 1.1.0 remains unreleased. These notes describe the draft Vault foundation and do not authorize merge, tagging, deployment, or consumer installation.

This release provides owner-local encrypted storage and agent-safe masked metadata. Agent plaintext delivery is not enabled until the harness can prove the destination and capture explicit owner approval.

Owner setup, protected record entry, unlock, attachment access, reveal, recovery, backup, restore, grant administration, rotation, deletion, and audit review run only in the human local TTY control plane. The model-facing command surface supports safe status, doctor, lock, and signed masked-metadata operations; other actions return `LOCAL_ACTION_REQUIRED` without reflecting input. Setup writes recovery material only to an explicit non-existing mode-`0600` file and confirmation remains separate.

The long Unix-socket fallback rejects symlinks, non-directories, foreign ownership, unsafe mode, and path replacement before creating its private alias. The release retains fail-closed agent reveal with `PRIVATE_CONTEXT_UNATTESTED`.

Before any stable release, obtain accountable maintainer review, resolve blocking findings, commission external security review for high-assurance claims, and explicitly approve merge and release as separate decisions.
