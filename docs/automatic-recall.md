# Automatic recall

MegaBrain recalls relevant private context without waiting for the agent to remember to ask. Supported agents run two local hooks: one when a session starts and one each time the owner sends a message. Each hook shows a one-line receipt, so the owner can see MegaBrain working:

```text
MegaBrain: connected · synced · 142 memories · 1 conflict needs you
MegaBrain: recalled 3 memories and 1 document
MegaBrain: nothing relevant
```

| Agent | Automatic recall | First use |
| --- | --- | --- |
| Claude Code | Hooks in `~/.claude/settings.json` | Starts with the next session. |
| Codex | Hooks in `~/.codex/hooks.json` | Open `/hooks` in Codex once and trust MegaBrain's two hooks. Codex skips new or changed hooks until the owner trusts them. |
| Hermes | Not available | Keeps instruction-driven retrieval. |

Setup and connect install the hooks. An existing connection receives them on its first ordinary read after updating to a release that includes automatic recall, and reports a one-time `automatic_recall_update.notice`. Disconnect removes only MegaBrain's entries. Other settings and hooks are preserved. A settings file that is not valid JSON, or that cannot be written, is left untouched and reported. MegaBrain tries again on a later read once it is fixed. A linked settings file is edited in place, keeping the link.

## What the hooks do

**Session start** synchronizes, then gives the agent a short briefing:

- that MegaBrain is connected and how many current memories it holds;
- an instruction to search MegaBrain before telling the owner it has no information about them, their people, projects, preferences or past decisions;
- the most relevant memories and documents for the project the session is working in, named from the repository or folder. The path itself is never included.

It also runs the daily runtime update check that ordinary reads already perform.

**Each message** searches current memories and document sections using the owner's actual words, not an agent's summary of them. The relevant results are given to the agent as context, labelled as data, never as instructions. When nothing matches, the agent is told to search again with different words before claiming it has no information. Conflicting claims are always recalled together with an instruction to ask the owner.

The hooks skip:

- short acknowledgements such as "ok" or "go", and slash commands;
- any message that looks like it contains a secret. The receipt reports the skip and nothing is recorded.

A hook never blocks the agent's turn. On any failure it reports `MegaBrain: unavailable this turn` and the conversation continues. The installed command exits successfully even when the helper is missing or an older runtime doesn't recognize it, because Claude Code treats one specific failure code as "block this message".

## Freshness

Agents keep writing exactly as before: every save is pushed immediately. Explicit reads such as `megabrain search` still synchronize first. Automatic recall uses the local copy when it is recent, because synchronizing on every message would add about a second to each one.

| Local copy last synchronized | Message behavior |
| --- | --- |
| Within 1 minute | Answer from the local copy. |
| 1 to 10 minutes ago | Answer from the local copy, then refresh it in the background for the next message. |
| More than 10 minutes ago, or unknown | Synchronize first, then answer. |
| Remote unreachable | Answer from the local copy and say so in the receipt. |

Session start always synchronizes. An agent can therefore miss something another agent saved in the last few minutes of an active conversation. The receipt shows the local copy's age whenever it is older than two minutes. Ask the agent to search MegaBrain to synchronize immediately.

Hooks download from the remote before taking the Brain lock, bounded to a few seconds, and only then integrate the result locally. A slow network therefore never makes another session or a save wait, and local Git operations are never interrupted. Hooks never upload inline. When a save is still waiting to upload, the receipt says so and a background refresh sends it. At most one background refresh starts every 30 seconds.

## Activity and "is it working?"

Each lookup appends a value-free receipt to ignored local state in the agent's clone (`.megabrain/activity/`). This covers automatic recall, `search` and `context`. A receipt holds:

- the time, the event and whether the lookup was automatic or agent-initiated;
- whether anything was found;
- the IDs of the memories and documents used, and the number of conflicts;
- the duration and the freshness mode.

It never holds message text, queries, summaries or excerpts. Receipts are kept for three months.

```sh
megabrain activity            # last 7 days for this agent on this device
megabrain activity --days 30
megabrain status              # includes automatic_recall: hooks state and recent use
```

Background refreshes and `megabrain open` also publish these receipts to the `megabrain-activity` branch of the private Brain repository, at most every 30 minutes and only when they changed. Home and Live Home then show every agent's use on Today. See [owner workflows](owner-workflows.md#agent-activity).

## Privacy

Hooks run the installed helper through the agent's own skill link, so the existing trusted-context, relevance and policy checks apply unchanged. Private memories are recalled only for owner-local Codex and Claude agents with an approved read policy, and only when relevant to the message. Hermes and source-tree calls remain general-only. Message text is passed to the local helper over standard input and is not stored. No service, daemon or network relay is involved.

## Cost

See the [benchmark](benchmarks/automatic-recall-2026-11-08.md). In short, a recall within the freshness window makes no network calls and its cost does not grow with a Brain's size. The agent also no longer spends one or two model steps of its own on lookups.

The added context is bounded to about 3,600 characters per message and is empty apart from a short search reminder when nothing is relevant. Explicit reads also got faster. They no longer push when there is nothing to send, and they validate a committed tree only once.

## Turning it off

Disconnecting an agent removes its hooks. To keep MegaBrain connected without automatic recall, remove the two MegaBrain entries from the agent's hook settings. In Codex, you can also disable them in `/hooks`. The agent then falls back to its MegaBrain instructions. Hand-removed entries stay removed through later reads and updates; connecting the agent again restores them.
