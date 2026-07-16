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

Metadata, location awareness, internal use, plaintext reveal, write, attachment, deletion, and administration are separate policy actions. Metadata requests require both their global scope and matching resource scope. Reveal scopes are reserved for a future harness-attested channel and do not enable agent reveal in this release. Optional resource-class restrictions further narrow a grant.

## Signed requests

Every agent request includes schema, registered agent ID, method, logical resource, selected fields, structured purpose code, structured context, Unix timestamp, random nonce, and random request ID. The Ed25519 signature covers the complete canonical JSON request. The broker rejects missing grants, revoked grants, invalid signatures, timestamps outside 60 seconds, repeated request IDs or nonces, missing scopes, disallowed classes, and unsupported methods.

An agent signature proves who made a request; it does not prove where output will appear. Therefore the broker rejects every agent reveal with `PRIVATE_CONTEXT_UNATTESTED`, including a signed self-assertion of `context.kind: private`. Metadata remains available and returns only protected, type-specific projections. Plaintext owner reveal is confined to the human local TTY control plane. A future harness integration must provide independently verifiable destination attestation and exact owner approval before agent delivery can be enabled.

This release provides owner-local encrypted storage and agent-safe masked metadata. Agent plaintext delivery is not enabled until the harness can prove the destination and capture explicit owner approval. Agent-mediated setup, secret entry, unlock, owner reveal, recovery, backup, and restore return `LOCAL_ACTION_REQUIRED`; neither agent JSON nor chat is a protected input channel.

## Broker

The owner unlocks a same-host Unix-domain broker with passphrase or recovery material on standard input. The broker holds the master key only in memory, serves authenticated metadata, and locks explicitly or after 5–3600 seconds of inactivity. Per-client read deadlines prevent an incomplete frame from suspending the idle lock; a process lock serializes startup. It never binds TCP or HTTP. Unix file ownership protects the socket but is not the agent identity control; signed application requests are still required.

## Auditing and revocation

Every allowed and denied sensitive request records timestamp, agent, action, keyed resource reference, outcome, stable reason code, and request ID. Values, original logical IDs, signatures, keys, and free-form sensitive purpose are excluded from audit output.

Revocation changes policy immediately for future requests. It cannot erase plaintext already returned to the agent, captured by another program, or retained in model/tool context. Rotate an agent grant by issuing a new keypair and policy version; never copy private keys between agents or commit them.
