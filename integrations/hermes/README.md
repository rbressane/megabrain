# MegaBrain Vault for Hermes

This directory contains the standalone Hermes integration for MegaBrain Vault private delivery. It is not copied into the Hermes core tree. Install the `megabrain-vault` directory as a user plugin only after reviewing its trusted-computing-base role, then explicitly enable it with `hermes plugins enable megabrain-vault`.

## Compatibility boundary

The plugin requires MegaBrain runtime 1.2 and Hermes session provenance from the generic upstream change in [NousResearch/hermes-agent#65338](https://github.com/NousResearch/hermes-agent/pull/65338). It checks for task-local `HERMES_SESSION_SOURCE` and `HERMES_SESSION_CHAT_TYPE` bindings and remains hidden without them. A session ID, prompt claim, process environment value, or captured pre-authentication event is not sufficient.

The tool is visible only while:

- the encrypted harness state has been owner-locally unlocked into the gateway process;
- the same-host Vault broker is unlocked;
- Hermes classifies the current turn as `gateway_user` and `dm`;
- the captured authorized event exactly matches the task-local platform, user, chat, thread, message, and session bindings.

Internal/background, API, cron, group, channel, forum, email, delegated, unattended, unknown, mismatched, and unpaired-owner contexts fail closed.

## Model and approval flow

The model can call `megabrain_vault` with exactly four fields: `action`, `resource`, `fields`, and `purpose`. The JSON Schema and core validator both reject destination IDs, approval/private flags, keys, signatures, attestations, hosts, URLs, commands, timeouts, or values.

For `deliver` or `use`, the first call returns only an `approval_required` receipt. The trusted adapter separately renders the exact resource label, fields, purpose, requester, destination class, warning, expiry, and `/megabrain-approve <approval-id>` command directly in the paired owner DM; the model cannot rewrite that approval UI. The slash command is handled after Hermes authorization and outside the model turn. It reuses the original request/approval IDs, signs the live approval-command message context, asks Vault for a sealed release, and opens it only inside the matching adapter. Plaintext and sealed ciphertext never become a model tool result.

There is no session, destination, field, or permanent approval option, and Hermes `--yolo` does not bypass this plugin-owned approval.

## Owner-local controls

Pairing and key management are interactive local commands. Passphrases use no-echo prompts and never enter arguments, environment variables, chat, logs, or JSON output.

```text
hermes megabrain-vault pair
hermes megabrain-vault unlock
hermes megabrain-vault status
hermes megabrain-vault lock
hermes megabrain-vault rotate --grace-seconds 300
hermes megabrain-vault rollback --issuer-instance <id> --restore-key-id <id> --revoke-key-id <id>
hermes megabrain-vault revoke --issuer-instance <id> --key-id <id>
```

`pair` prompts locally for the exact platform/user/chat/thread identifiers so they do not enter chat or shell arguments. The gateway starts a mode-`0600` same-host Unix-socket control endpoint lazily after a real inbound message. `unlock` sends the harness passphrase from the owner TTY to that gateway process, which decrypts the active Ed25519/digest keys into memory. The encrypted state file is mode `0600`; raw destinations and private keys are inside its XChaCha20-Poly1305 wrapper. Five failed unlocks in 60 seconds fail closed. `lock`, rotation, rollback, and revocation discard in-process authority and pending approvals.

The owner must separately unlock Vault through its own local control plane. Harness unlock does not unlock Vault.

## Direct use

The integration exposes only the core no-network `synthetic.token-check` adapter (`api.example.invalid`, `token-check`, exact fields, five-second timeout). It does not provide arbitrary shell, HTTP, OAuth, browser, URL, executable, environment, or real-provider adapters. A future real adapter requires separate review and an owner-local exact capability grant.

## Trust and limitations

Hermes plugins execute in process and are part of the trusted computing base. Attestation proves what the paired plugin signed; it cannot make a malicious installed plugin honest. A compromised same-user process, debugger, memory inspector, platform adapter, or owner device remains outside the protection this Python integration can guarantee. Python cannot promise perfect zeroization. Platform delivery may persist the approved value according to that platform's own retention and notification behavior. Revocation blocks future releases but cannot recall a delivered message or completed provider effect.

The plugin must be tested with synthetic values only. Do not point development tests at a private Brain, real Vault, or real destination.
