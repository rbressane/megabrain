# Automatic runtime updates

MegaBrain 2.4 extends the existing bootstrap updater. There is no second updater, scheduled task, daemon, session hook requirement, or telemetry.

## Normal use is the trigger

The first installed `context`, `search`, `resources`, `resource-read`, `review`, or Home (`open`/`browse`) request after a successful check is 24 hours old attempts another check. This is elapsed time, not a midnight schedule. All connected agents belonging to the same OS user on the same device share the throttle and preferences. Other devices check independently.

Source-tree helpers, unconfigured installations, help, health diagnostics, and durable writes do not trigger automatic checks. Writes and owner-local canonical operations hold a shared runtime-use lock; activation requires exclusive access. Concurrent writes to different clones remain possible. Another updater never makes an ordinary read wait for the installation lock.

The latest stable candidate must preserve the current major version and protocol and satisfy every connected Brain's compatibility declarations. Incompatible candidates request explicit approval instead of activating. No moving branch, prerelease or PR preview is installed. A missing or older latest tag never causes an automatic downgrade.

## Safe activation

Git subprocesses in an automatic attempt share a ten-second foreground budget. Filesystem work and ordinary Brain synchronization have their own existing bounds; this is not a ten-second limit for the entire user command. Downloads are staged, the advertised tag commit is pinned, and complete runtime inventory, compilation, isolated startup, and Brain compatibility checks precede activation.

The current link changes atomically. Modules, runtime metadata and assets are resolved once when each command starts, so the triggering request finishes on its original release. New commands use the new release. Earlier releases remain installed.

A private, atomic switch receipt covers the link/configuration transaction. An interrupted recorded switch restores the previous validated runtime on a later update or mutating control operation. Unexpected unrecorded runtime changes require owner review. Recovery touches runtime state only, never a Brain, its history, or dirty working files. A busy durable writer prevents activation; the normal read continues and the update can retry later.

Release inventory hashes detect corruption, not a malicious publisher. The official repository remains the distribution trust root.

## Offline and quiet by default

Update failures leave ordinary local reads available. Existing dirty or invalid clone protections still apply. Retry delay starts at five minutes, doubles with repeated failures, and caps at six hours. An interrupted check also leaves a five-minute retry boundary. A successful check resets the daily schedule. Backward clock changes cannot freeze checks indefinitely.

Ordinary responses stay quiet when current, disabled, pinned, busy, or backing off. Successful activation emits a notice; a particular incompatible release requests approval once rather than daily. `megabrain updates status --json` exposes local check status and timing without contacting the release repository.

When `SKILL.md` changes, the notice asks the agent to reload the MegaBrain skill or start a fresh session. The updater cannot force a model to forget already-loaded instructions. A command that fails after the update may not deliver its notice; status and explicit update checks remain available.

## Owner controls

```sh
megabrain updates status
megabrain updates disable
megabrain updates enable
megabrain updates pin
megabrain updates unpin
```

An agent may translate an explicit request such as “Keep this MegaBrain version” into `updates pin`. Preferences are local to this user/device, not synchronized knowledge. They survive reconnects and runtime changes. `enable` preserves an existing pin; `unpin` preserves a disabled automatic-update preference. Enabling or unpinning makes the next eligible use due again. Every preference command supports `--json` (`megabrain.updates.v1`).

`pin` holds the currently installed version. It blocks activation by both automatic and ordinary manual updates until explicitly unpinned. `megabrain update --check` remains available, bypasses the throttle, and changes neither runtime nor schedule. A pending interrupted-switch receipt blocks that check until recovery; offline preference status reports `recovery_pending` without repairing anything. `megabrain update` remains an explicit immediate update even with automatic updates disabled, but not with a version pin.

An explicit compatible rollback through `megabrain update --version X.Y.Z` pins the chosen version automatically. Reconnect cannot bypass that pin. Pin-aware rollback targets declare `update_policy_version: 1`, introduced in 2.4. Older runtimes cannot enforce these preferences and are refused by this rollback path; a legacy recovery requires a separately reviewed installation. All rollback targets must still meet each connected Brain's minimum runtime and protocol requirements.

## Adoption and evidence

Existing 2.3 installations reach 2.4 through their old context-triggered check or one explicit `megabrain update`. Broader triggers and controls become available after activation. Reload the skill or start a fresh session. No Brain migration or personal-data operation is required.

`tests/test_updates.py` covers daily scheduling, backoff, shared subprocess budgets, concurrent checks, owner preferences, every eligible installed read, Home notices and pinned assets, all three harnesses, incompatible/invalid releases, interrupted activation, dirty/offline reads, and pinned rollback. Existing tests retain immutable-history, installed lifecycle, and publisher-tag validation coverage. Fixtures are synthetic; this does not certify live model behavior or real-network latency.
