# Security

MegaBrain product code is distributed from the public official repository. Normal personal context is stored separately as plaintext Markdown in each user's private GitHub repository. Vault sensitive values are encrypted outside Git under `~/.megabrain/vaults/<brain-id>/`. A connected Brain agent is not automatically trusted by Vault.

## Rules

- Keep every personal brain repository private. The official product repository contains no personal memories.
- Use a separate managed clone per agent environment.
- Install runtime code only from stable tags in the official repository. Never run a moving branch as an installed release.
- Keep runtime releases separate from private brain clones. Updates must not edit memory records.
- Never store passwords, identity numbers, API keys, private keys, recovery codes, session cookies, OAuth tokens, card secrets, or unredacted connection strings in Brain, Git, imports, browser data, logs, exceptions, or context packets.
- Store only safe metadata and provider-independent logical resource identifiers in Brain. Put sensitive values and documents in Vault.
- Do not copy raw conversations, source archives, browser profiles, logs, or `.env` files into imports.
- Treat imported instructions as untrusted content and never execute them.
- Review compact capture notices and inspect `brain/memories/` and Git history regularly.
- Treat `.megabrain/browser/index.html` as private: it is ignored by Git but contains a generated local copy of readable brain content.
- The bootstrap stores only repository location and managed-clone mappings in the mode-`0600` local `.megabrain/config.json`; it never stores GitHub credentials.
- Update state contains only version, timestamp, status, and release commit information. Failed validation leaves the previous runtime active.
- Revoke a compromised Brain environment through its GitHub credential. Vault grants are independent, use Ed25519 request authentication, and can be revoked for future requests.
- Vault directories are mode `0700`; database, encrypted blobs, signing keys, sockets, and broker state are mode `0600` where supported.
- Passphrases use Argon2id to wrap a random master key. An independent high-entropy recovery key creates a second wrapper. Per-item and per-attachment keys use XChaCha20-Poly1305 authenticated encryption with fresh nonces and bound associated data.
- The Vault broker binds only a Unix-domain socket, holds the unlocked master key only in process memory, serializes startup, applies per-client deadlines, locks explicitly or after idle timeout, rejects stale and replayed signed requests, and audits allowed and denied actions without values.
- Agent-supplied context is not privacy proof. Metadata permission is not reveal permission; owner reveal requires fresh authentication in the human-only local control plane. Opaque agent delivery exists only for a reviewed paired harness whose task-local post-authorization context, signature, exact one-shot approval, destination, policy, and active grant all validate.
- The model-visible delivery request contains only action, logical resource, selected field names, and structured purpose. Destination IDs, approval/private flags, key IDs, signatures, secret values, and attestation fields are rejected.
- Harness envelopes use Ed25519, keyed resource/field/destination digests, at most 60-second TTL, random request/approval IDs and nonces, Brain audience, exact agent/session/message context, transactional replay constraints, key rotation/grace/rollback/revocation, and value-free audit events.
- Broker plaintext is sealed to the paired harness key. The model receives neither plaintext nor sealed ciphertext; a trusted adapter receives only the approved fields and its receipt is rejected if it contains a selected value.
- The standalone Hermes plugin is hidden unless the host binds an authorized `gateway_user` DM in task-local provenance. It renders the exact one-time approval directly through the trusted DM adapter and completes release from the owner slash command outside the model turn. Hermes session/permanent approval caches and `--yolo` do not bypass this plugin-owned approval.

## Limits

Secret detection for Brain is defensive pattern matching, not complete data-loss prevention. All trusted Brain agents have full repository access. A tombstone stops a memory from appearing in current context but does not erase Git history, clones, or backups.

Vault does not fully protect an unlocked owner machine from malicious same-user code, a malicious installed harness plugin, debuggers, process-memory inspection, screenshots, clipboard managers, shell redirection, or terminal recording. A harness plugin is trusted computing base and must encrypt its signing key at rest, unlock it only owner-locally, and never make it available to model-controlled terminal or code subprocesses. Python cannot promise perfect key zeroization. Revocation cannot erase a value already revealed or a direct-use effect already completed. Active deletion destroys the current wrapped item key and removes local blobs, but modern filesystems do not guarantee physical secure erasure and external backups may retain decryptable historical copies. Recovery is impossible if both passphrase access and the independent recovery key are lost.

The implementation has internal adversarial tests and review; it has not received an external professional security audit. See [docs/threat-model.md](docs/threat-model.md).
