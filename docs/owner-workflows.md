# Owner workflows

## Inspect, then change

Home remains a private static snapshot. Its graph-first overview leads to current memories and their history. Resources lists approved current documents and runbooks with immutable citations and inert source text. Needs review highlights uncertainty, conflicts, possible duplicate summaries, missing review dates and old verification evidence. Project filters narrow both memory and resource views.

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

## Agent health

The Agents view distinguishes a configured private-read policy from registration. Neither registration nor a static snapshot is proof that an agent is online. Ask that agent to run `megabrain status`; use `doctor` for failure details. Private access still depends on the exact active policy, scope, trusted context and relevance.
