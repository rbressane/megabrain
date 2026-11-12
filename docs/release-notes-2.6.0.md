# MegaBrain 2.6.0

Automatic recall, a readable Today page and an optional owner view in Live Home. Runtime protocol remains 2; no Brain migration is required.

## Automatic recall (Claude Code and Codex)

- Setup and connect install two local hooks: session start and every owner message. Hermes keeps instruction-driven retrieval.
- Every owner message runs the unified memory and document search on the owner's own words. Results reach the agent as context labelled as data, never as instructions. Weak single-term matches are not injected, and conflict companions are recalled together.
- Every turn shows a receipt, such as `MegaBrain: recalled 2 memories and 1 document` or `MegaBrain: nothing relevant`, and says when the local copy is stale or offline. When nothing matches, the agent is told to search again with different words before saying it lacks the information.
- Acknowledgements, slash commands and secret-shaped messages are skipped and leave no record. A hook never blocks a turn.
- Existing connections receive the hooks on the new runtime's first ordinary read and see a one-time notice. Codex owners trust the two hooks once in `/hooks`. Hooks the owner removes stay removed until an explicit connect.
- Protocol invariant 1 (owner-approved): automatic per-message recall may answer from the last validated synchronized copy while it is at most ten minutes old. Explicit context reads still pull first. All write, trust, relevance and policy gates are unchanged.

## Faster reads

- Reads push only when local commits are pending.
- A clean committed tree is validated once per tree and runtime; only successes are cached.
- Automatic recall answers from the local copy for one minute, refreshes in the background between one and ten minutes, and synchronizes first after ten minutes. Hooks never push inline.

## Visible use

- `megabrain activity` lists this agent's lookups on this device, found and not found, and the most-recalled memories. `megabrain status` reports `automatic_recall`.
- Receipts are local mode-0600 state holding identifiers and counts only, never message text, queries or excerpts, kept for three months.
- Agents publish these value-free receipts to the private Brain repository's `megabrain-activity` branch, at most every 30 minutes, so Home can show every agent's use. The branch is a replaceable projection updated with `--force-with-lease`, never a plain force.

## Today page and Console design

- Local Home and Live Home open on **Today**: whether the Brain is up to date, what needs the owner (conflicts and reviews), how each agent used it this week, what was recently learned, changed or forgotten, and what MegaBrain knows. The graph moves to **Map**.
- A retro-futuristic Console design with larger reading type, a light and dark theme toggle, and one bundled Geist Mono font (SIL OFL) that makes the page smaller than before.

## Live Home owner view

- Live Home stays general-only by default. Started with `--owner-private` after the owner's explicit approval, it shows the signed-in owner their general and private memories and resources, each private item marked. Sensitive records, raw imports, policies, attachments and repository files are never served.
- The scope comes only from the start-up flag; no request can widen it, and the viewer refuses a projection containing anything outside its scope. The status strip and the sign-in page name the active scope.
- The owner view is the owner reading their own Brain. It grants no agent any permission and does not change agent read policies.
- The Live Home runbook adds a Linux systemd supervision reference with fictitious names.

## Upgrade fixes

- Owner-local tools find the Brain through a harness skill link again. A configured clone reached from outside a skill link reports `CLONE_NOT_RESOLVED`.
- `migrate-v1` applies the same identity upgrade as `connect`, so private recall works after migration. A policy with history is never recreated.
- Every not-ready capability in `status` and `doctor` carries a `remediation` with the exact command.
- Runtime validation for 2.6.0 and newer requires the recall, integration and activity modules and the bundled font.

## Verification and boundaries

Local release verification passed the unit suite, seed validation and the static and Live Home Chromium checks with synthetic data. The GitHub matrix covers macOS and Linux on Python 3.10, 3.11 and 3.13 plus browser verification. Actions now validate pushes only on `main` and version branches; pull requests run the full matrix.

No personal Brain was used or connected. Publishing v2.6.0 does not authorize connecting a personal replica or enabling the owner view on any host. Private Git is not encryption. Vault, sensitive synchronization, attested delivery and Hermes private provenance remain independently gated.
