# Architecture

MegaBrain has no running service. It consists of a versioned local runtime and isolated clones of one private data repository.

## Runtime

The official product repository publishes stable Git tags. Setup copies a selected release under `~/.megabrain/runtime/releases/<version>` and atomically points `~/.megabrain/runtime/current` at it. Harness skill links point through `current`, so a validated release switch takes effect without editing a live runtime. Failed downloads or validation leave the current release active.

The runtime checks for compatible releases at most once per day during normal context retrieval. It never follows `main`. Major updates require approval, and an explicit version can be activated for recovery.

## Private Brain

Each supported agent has a clone under `~/.megabrain/clones/<harness>`. New private repositories contain `brain/`, `megabrain.json`, and private-brain documentation. They do not contain GitHub Actions workflows or the executable product runtime.

The installed helper pulls before context retrieval, resolves the immutable memory graph, and performs lexical task matching. Write operations create new Markdown records, validate and secret-scan them, commit only those records, and push. Unique filenames let rejected concurrent pushes fetch, rebase, and retry without modifying shared memory files.

Each clone stores an ignored `.megabrain/local.json` identity. Its provenance record lives under `brain/agents/`. If GitHub is unavailable, reads use local state and writes remain committed locally for a later retry. Unexpected clone edits block automatic rebasing.

If first setup creates a local seed but the initial push fails, rerunning setup after authorization is repaired pushes the clean local seed into the still-empty remote instead of discarding local state or requiring manual Git repair. A pristine, unpushed v1.0.0 seed is recognized exactly and has its legacy validation workflow removed from the root commit before synchronization. Any dirty worktree, additional commit, changed seed content, unexpected remote history, or unreachable remote blocks that migration without modifying the clone.

## Compatibility

`skill/megabrain/runtime.json` declares the installed version and supported protocol. A private brain's `megabrain.json` declares its protocol and minimum runtime. A runtime may read a compatible older protocol but refuses new writes when it is below the brain's minimum version. Runtime updates never migrate or rewrite memory files.
