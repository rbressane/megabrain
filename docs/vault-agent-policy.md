# Vault Agent Policy

Brain access and Vault access are independent. A newly connected agent receives no Vault scope. Granting an agent creates a local mode-`0600` Ed25519 private key under the managed clone's ignored `.megabrain/` state and stores only its public key, fingerprint, scopes, classes, and policy state in Vault.

## Global scopes

```text
vault.metadata
vault.locate
vault.reveal
vault.write
vault.attach
vault.delete
vault.admin
```

## Resource scopes

```text
identity.metadata
identity.reveal
credentials.use
credentials.reveal
health.metadata
health.reveal
finance.metadata
finance.reveal
```

Metadata, location awareness, internal use, plaintext reveal, write, attachment, deletion, and administration are separate policy actions. Metadata requests require both their global scope and matching resource scope. Reveal scopes do not enable the normal agent reveal method; they are checked again only inside the separate harness-attested release path. Optional resource-class restrictions further narrow a grant.

## Signed requests

Every agent request includes schema, registered agent ID, method, logical resource, selected fields, structured purpose code, structured context, Unix timestamp, random nonce, and random request ID. The Ed25519 signature covers the complete canonical JSON request. The broker rejects missing grants, revoked grants, invalid signatures, timestamps outside 60 seconds, repeated request IDs or nonces, missing scopes, disallowed classes, and unsupported methods.

An agent signature proves who made a request; it does not prove where output will appear. Therefore the normal broker reveal method rejects every agent reveal with `PRIVATE_CONTEXT_UNATTESTED`, including a signed self-assertion of `context.kind: private`. Metadata remains available and returns only protected, type-specific projections.

The separate `attested.release` path accepts only the model's four value-free request fields plus an independently signed harness envelope. That envelope binds the active harness key, Vault audience, agent, session, message, source class, exact paired destination, action, keyed resource and field digests, purpose, policy, capability, one-shot approval, nonce, and expiry. Vault consumes it transactionally and returns ciphertext sealed to the harness key. The harness opens that ciphertext only at the trusted adapter boundary; neither the model result nor the normal agent response contains plaintext.

Owner-local encrypted storage and agent-safe masked metadata remain the default. A paired harness can enable an explicitly configured `private_dm_opt_in`, `local_secure_ui`, or bounded `direct_use_only` path only after exact one-time approval. Group, channel, forum, email, cron, webhook, delegated, unattended, background, API, internal, unknown, unpaired-owner, stale, tampered, replayed, and revoked contexts fail closed. Agent-mediated setup, secret entry, unlock, ordinary owner reveal, recovery, backup, and restore return `LOCAL_ACTION_REQUIRED`; neither agent JSON nor chat is a protected input channel.

## Broker

The owner unlocks a same-host Unix-domain broker with passphrase or recovery material on standard input. The broker holds the master key only in memory, serves authenticated metadata, and locks explicitly or after 5–3600 seconds of inactivity. Per-client read deadlines prevent an incomplete frame from suspending the idle lock; a process lock serializes startup. It never binds TCP or HTTP. Unix file ownership protects the socket but is not the agent identity control; signed application requests are still required.

## Auditing and revocation

Every allowed and denied sensitive request records timestamp, agent, action, policy, keyed resource/field/destination references, outcome, stable reason code, request ID, and approval ID. Values, original logical or destination IDs, signatures, keys, and free-form sensitive purpose are excluded from audit output.

Revocation changes policy immediately for future requests. It cannot erase plaintext already returned to the agent, captured by another program, or retained in model/tool context. Rotate an agent grant by issuing a new keypair and policy version; never copy private keys between agents or commit them.
