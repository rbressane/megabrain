# Owner workflows

## Inspect, then change

Local Home remains a private static snapshot. Optional [Live Home](live-home.md) refreshes committed general knowledge through a separate owner-authenticated URL, plus private records when the owner has approved its owner view. Both remain read-only. They open on Today, which states in plain sentences whether the Brain is up to date. It then lists conflicts and review reminders that need the owner, how each agent used MegaBrain this week, what was learned, changed (old and new wording) or forgotten in the last two weeks, and the most important current knowledge. The topic graph is under Map. Today also shows three meters (how often lookups found something, how much is confirmed, how much was used this week), a gauge for each agent, and a dial of the last two weeks with a running clock since the last synchronization. Home opens in its day theme, and the viewer can switch to a night theme. Resources lists approved current documents and runbooks with immutable citations and inert source text. Needs review highlights uncertainty, conflicts, possible duplicate summaries, missing review dates and old verification evidence. Project filters narrow both memory and resource views.

Review signals are advisory. No fact expires, merges or becomes confirmed automatically. A runbook/project resource whose verification is older than 90 days receives a reminder; `freshness_at` remains evidence metadata, not a reinterpreted expiration date. Memories use explicit `review_after` timestamps. A commitment or project-state memory without one is flagged for owner review. Stable preferences need no artificial expiry.

`megabrain review` returns up to 50 authorized review items by default. `megabrain review --stdin` accepts a `limit` from 1 to 100 and reports truncation. New memories may use `authority_domain`, `verified_at`, and `review_after`. Agent observations default to inferred confidence when confidence is omitted; imports default to unconfirmed. Unicode/case normalization reduces mechanical duplicates, but MegaBrain does not guess semantic equivalence or merge subjects automatically.

## Correct and forget

Home's Prepare correction, Prepare forgetting and Prepare resource review actions generate a copyable request only. Clipboard failure selects the request for manual copying. Dismiss returns to the current view. Nothing changes until the owner and connected agent review the current record and approve an immutable correction or tombstone. Resource changes continue through owner-local approval.

```sh
printf '%s' '{"action":"correct","id":"MEMORY_UUID"}' | megabrain handoff --stdin
```

The helper validates the target against the authorized committed view and returns a proposal with an immutable citation. It does not include arbitrary record text as executable instructions. A stale snapshot or historical memory cannot authorize a new mutation.

## Capture controls

Ask a connected owner-local agent to pause or resume automatic capture, or use:

```sh
megabrain capture pause
megabrain capture status
megabrain capture resume
```

The setting applies to **this agent on this device**, not all replicas. It is ignored local state, not synchronized canonical knowledge. Home and status report its scope. A malformed setting blocks automatic capture until reviewed.

`remember` defaults to `"capture":"automatic"`. Paused automatic writes return `created:false`. Use `"capture":"explicit"` only when the owner explicitly asks to remember an item; it can still save while automatic capture is paused. `"capture":"skip"` records nothing and honors an explicit don't-remember request. These controls guide trusted agents; they cannot constrain a process with unrestricted clone access.

## Agent activity

Agents publish value-free lookup receipts to the `megabrain-activity` branch of the private Brain repository. These are counts, times and the IDs of recalled memories and documents, never message text. Home and Live Home combine them, so Today and Agents show real use instead of registration alone.

The branch is a replaceable projection, not knowledge or history:
- each publish replaces it with a single commit, using a lease against the state it was built from;
- each agent writes only its own directory;
- other agents' receipts are strictly validated before use;
- a memory is named only when the viewer is allowed to see it.

Background refreshes publish at most every 30 minutes, and `megabrain open` publishes before generating Home. See [automatic recall](automatic-recall.md).

## Agent health

The Agents view distinguishes a configured private-read policy from registration. Neither registration nor a static snapshot is proof that an agent is online. Ask that agent to run `megabrain status`; use `doctor` for failure details. Private access still depends on the exact active policy, scope, trusted context and relevance.
