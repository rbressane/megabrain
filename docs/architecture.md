# Architecture

MegaBrain has no running architecture. It is a private Git repository cloned once per agent environment.

The installed skill calls a standard-library Python helper. `context` pulls, resolves the immutable memory graph, and performs lexical task matching. Write operations pull, create new Markdown files, validate and secret-scan them, commit only those files, and push. Rejected pushes fetch, rebase, and retry because unique memory filenames normally merge without conflict.

Each clone stores an ignored `.megabrain/local.json` identity. The corresponding public provenance record lives under `brain/agents/`. Skill links and global instruction markers cause Codex, Claude Code, and Hermes to invoke the same protocol.

If GitHub is unavailable, reads use the last local state and writes remain committed locally. A later brain operation retries synchronization. Unexpected tracked changes block automatic rebasing.
