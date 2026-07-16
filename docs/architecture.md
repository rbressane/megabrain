# Architecture

MegaBrain consists of a versioned local runtime, isolated clones of one private Brain repository, and an optional encrypted Vault. Brain has no running service. Vault may run an explicitly unlocked same-host broker and never opens a network listener.

## Runtime

The official product repository publishes stable Git tags. Setup copies a selected release under `~/.megabrain/runtime/releases/<version>` and atomically points `~/.megabrain/runtime/current` at it. Harness skill links point through `current`, so a validated release switch takes effect without editing a live runtime. Failed downloads or validation leave the current release active.

The runtime checks for compatible releases at most once per day during normal context retrieval. It never follows `main`. Major updates require approval, and an explicit version can be activated for recovery.

## Private Brain

Each supported agent has a clone under `~/.megabrain/clones/<harness>`. New private repositories contain `brain/`, `megabrain.json`, and private-brain documentation. They do not contain GitHub Actions workflows or the executable product runtime.

The installed helper synchronizes before context retrieval, resolves the immutable memory graph, and performs deterministic lexical task matching. Ordinary reads have no default staleness window: a process lock coalesces only calls already waiting on the same synchronization, so normal cross-agent correction remains visible. A configurable successful-sync window is explicit opt-in; `fresh: true` bypasses it and reports `stale: true` on failure. Durable writes always synchronize immediately before committing and push immediately afterward.

After validation, an ignored local SQLite index is atomically compiled for the exact Brain Git commit. Weighted token postings cover subject, tags, and compact summary projections. Warm retrieval queries only matching projections and bounded `always` records; it does not parse every Markdown body. Relevance ranks before the `core` tie-breaker, the declared limit covers all ordinary results, and conflict expansion is explicitly capped. Diagnostic mode exposes runtime, synchronization, index, graph, ranking, serialization, and total stages.

Write operations create new Markdown records, validate and secret-scan them, commit only those records, and push. Unique filenames let rejected concurrent pushes fetch, rebase, and retry without modifying shared memory files.

Each clone stores an ignored `.megabrain/local.json` identity. Its provenance record lives under `brain/agents/`. If GitHub is unavailable, reads use local state and writes remain committed locally for a later retry. Unexpected clone edits block automatic rebasing.

If first setup creates a local seed but the initial push fails, rerunning setup after authorization is repaired pushes the clean local seed into the still-empty remote instead of discarding local state or requiring manual Git repair. A pristine, unpushed v1.0.0 seed is recognized exactly and has its legacy validation workflow removed from the root commit before synchronization. Any dirty worktree, additional commit, changed seed content, unexpected remote history, or unreachable remote blocks that migration without modifying the clone.

## Compatibility

`skill/megabrain/runtime.json` declares the installed version and supported protocol. A private brain's `megabrain.json` declares its protocol and minimum runtime. A runtime may read a compatible older protocol but refuses new writes when it is below the brain's minimum version. Runtime updates never migrate or rewrite memory files.

## Vault

`megabrain.json` carries a stable UUID `brain_id` for new brains. Explicit first-time Vault setup adds one to an existing brain through a normal compatible metadata commit; memory records are untouched. The local Vault lives at `~/.megabrain/vaults/<brain-id>/` with a SQLite ciphertext container, encrypted attachment blobs, runtime socket state, and value-free audit data.

The Vault master key is random. Argon2id derives a passphrase key that wraps it; an independent 256-bit recovery key creates a second wrapper. Each item and attachment receives a fresh random key wrapped by the master key. XChaCha20-Poly1305 associated data binds opaque IDs, keyed resource digest, version, purpose, and attachment chunk position. SQLite provides transactions and indexes, not encryption.

Logical identifiers are normalized and indexed only through HMAC-SHA-256 keyed by the unlocked master key. Original identifiers, labels, field names, values, filenames, MIME data, and sizes are inside authenticated ciphertext. Database-level plaintext reveals schema version, random IDs, timestamps, row counts, grant scopes, audit outcomes, deletion markers, and ciphertext sizes.

The broker binds a permission-restricted Unix socket inside the Vault runtime directory. It holds the master key only in memory, locks on request or idle timeout, verifies registered Ed25519 keys, binds signatures to the complete structured request, rejects stale timestamps and replayed request IDs/nonces, evaluates scopes and resource classes, and fails closed for non-private reveal contexts. Revocation affects future requests only.

Portable `.mbvault` files are ZIP containers holding a consistent encrypted SQLite snapshot, encrypted blobs, and a versioned digest manifest. Restore validates paths, every digest, database identity, cryptographic authentication, all active items, and attachment inventory in a temporary directory before atomic activation.

## Provider Boundary

The built-in store implements the default `SensitiveStore` behavior: put, metadata, reveal, attach, delete, export, and health. Future external providers may map the same logical identifiers. No 1Password, Bitwarden, KeePassXC, cloud KMS, marketplace, hosted relay, or automatic provider migration is implemented here.
