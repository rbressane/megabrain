# Vault Harness Attestation and Opaque Delivery

## Boundary

Agent text is never evidence of where output will go. A model cannot assert a private chat, name a destination, provide an approval flag, select a harness key, or submit an attestation. The only model-visible request schema is:

```json
{
  "action": "deliver",
  "resource": "identity://synthetic-subject/passport/current",
  "fields": ["document_number"],
  "purpose": "owner-request"
}
```

`action` is one of `locate`, `metadata`, `deliver`, or `use`. The other three fields are a provider-independent logical resource, a bounded allow-listed field-name list, and a structured purpose code. Extra fields fail closed. Secret values, destination identifiers, approval booleans, context claims, signatures, private flags, key IDs, and attestation objects are forbidden.

The release remains in containment mode when no trusted harness is paired: agents receive masked metadata only and secret-bearing operations return `LOCAL_ACTION_REQUIRED`.

## Trust sequence

1. The owner installs and reviews a harness adapter, creates a signing key and keyed-digest key outside model context, and pairs its public identity and exact owner destinations through a local authenticated action.
2. A live model turn submits only the value-free request above.
3. The harness reads task-local context that the host bound after authorization. It rejects missing, inherited, environment-only, subprocess-supplied, prompt-supplied, API, cron, webhook, delegated, unattended, background, internal, group, channel, forum, and email context.
4. The harness displays an exact one-shot approval containing the safe resource label, selected fields, purpose, requester, concrete destination description, boundary warning, request/approval IDs, and expiry. A gateway may resume those same trusted IDs after its exact out-of-band approval command; the model cannot supply them. There is no session-wide, destination-wide, field-wide, or permanent approval.
5. Only after approval, the harness signs a short-lived envelope. It binds schema, issuer instance, key ID, Brain audience, request ID, nonce, issue/expiry time, agent, session, message, provenance, platform, chat type, user, chat, thread, action, keyed resource and field digests, purpose, approval ID, delivery policy, direct-use capability ID, and exact destination digest.
6. Vault verifies every field, active/grace key state, audience, Ed25519 signature, keyed digests, owner-paired destination, resource policy, agent grant/scopes, direct-use capability, TTL, and one-shot request/nonce/approval uniqueness.
7. Vault consumes the approval before release, decrypts only the selected fields, and sealed-box encrypts them to the paired harness public key. The broker never emits plaintext JSON.
8. The trusted adapter opens the sealed release and passes the fields directly to the approved destination or bounded use adapter. The model receives only a value-free receipt.

## Attestation lifetime and replay

Attestations live for at most 60 seconds, accept at most five seconds of future clock skew, and use random 192-bit nonces plus UUID request and approval identifiers. `request_id`, `nonce`, and `approval_id` are unique database constraints. Concurrent duplicate delivery therefore permits at most one release. Expired, future, malformed, wrong-audience, unknown-key, revoked-key, bad-signature, tampered-resource, tampered-field, tampered-purpose, wrong-agent, wrong-session, wrong-message, and wrong-destination requests fail closed and produce value-free audit events.

## Pairing, rotation, rollback, and revocation

Vault stores only the harness public key and an authenticated master-key-wrapped digest key. The harness private signing key is never stored in Vault, Brain, Git, a model request, an environment variable, a subprocess argument, or a session database. A harness integration must encrypt its private material at rest and unlock it only through an owner-local no-echo control.

Rotation inserts the replacement key, destination bindings, and old-key grace state in one SQLite transaction. The owner chooses a grace window from zero to 3,600 seconds. Old attestations remain valid only inside that window. Rollback is allowed only while the prior key remains in grace and revokes the replacement atomically. Explicit revocation immediately blocks future attestations and revokes its paired destinations; it cannot recall a release already delivered.

## Opaque release

The unlocked same-host broker accepts `attested.release` internally. Its response contains a sealed box, request ID, and approval ID—not plaintext fields. Only the paired Ed25519 signing key converted to its Curve25519 form can open that box. The trusted adapter must compare the request, approval, and destination binding, clear transient mappings after delivery, and reject any receipt containing a selected value.

Ciphertext is not returned to the model either. The harness tool handler opens and delivers it internally and returns a receipt such as `{"ok":true,"delivered":true,"action":"deliver"}` with platform-safe message metadata. Logs, errors, telemetry, audits, browser output, Git, and session persistence receive neither plaintext nor sealed payloads.

## Migration

Vault schema 1 migrates transactionally to schema 2 on first open. The migration adds harness keys and destinations, per-resource delivery policies, direct-use capabilities, one-shot attested-request state, and value-free delivery audit events, then updates both `vault_header.schema_version` and SQLite `user_version`. Existing encrypted items, attachments, grants, recovery wrappers, and backups are unchanged. A schema-2 backup restores only into a runtime that supports schema 2; downgrade is fail-closed.

See [vault-delivery-policy.md](vault-delivery-policy.md), [vault-direct-use.md](vault-direct-use.md), and [threat-model.md](threat-model.md).
