# Vault Delivery Policy

Delivery policy belongs to each encrypted resource and is set only in the local owner control plane with the `delivery-policy` action. The default is derived conservatively from the logical resource class.

| Policy | Meaning |
|---|---|
| `metadata_only` | Masked metadata may be located; plaintext release is denied. |
| `local_secure_ui` | Selected plaintext may appear only in the owner-local secure interface after exact approval. |
| `private_dm_opt_in` | Selected plaintext may go only to an exact paired live owner DM after a fresh warning and approval. This is never a default. |
| `direct_use_only` | Selected credential fields may enter only a registered bounded adapter; reveal and DM delivery are denied. |
| `never_reveal` | Plaintext release and direct use are denied. |

Defaults:

- credentials: `direct_use_only`;
- recovery material: `local_secure_ui` (or `never_reveal` by owner choice), never DM;
- identity, health, and finance: `local_secure_ui`;
- unknown classes: `never_reveal`.

Credentials cannot be changed to a reveal policy. Recovery material cannot be changed to DM or direct-use delivery. Private DM opt-in is intended for a specific non-credential resource only; it records a warning that the selected fields will leave the owner-local device boundary.

The destination allow-list is keyed and exact: platform, DM chat type, owner user ID, chat ID, and thread ID. A correct platform with the wrong owner, chat, or thread fails. Session ID and triggering message ID are additionally bound into each short-lived attestation. Groups, channels, forums, email, API requests, webhooks, cron, delegated tasks, unattended jobs, background completions, and internal/system turns are denied even when they reuse a known session identifier.

Policy changes affect future approvals only. They do not invalidate plaintext already delivered, modify exported backups, or prove deletion from a destination.
