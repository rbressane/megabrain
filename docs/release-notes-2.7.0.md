# MegaBrain 2.7.0

A weekly digest the owner approves. Runtime protocol remains 2; no Brain migration is required.

## Weekly digest

- Once a week MegaBrain gathers what needs the owner's attention:
  - open conflicts to settle;
  - near-duplicate memories to merge;
  - uncertain memories saved that week to confirm;
  - reviews that are due.

  It also lists what was learned, changed (with the earlier wording) and forgotten, and how many lookups found nothing.
- Home and Live Home show it as a "This week" card on Today. Each suggestion has a "Prepare for your agent" button that copies a request to hand to an agent. Another button lets the owner go through all of them with an agent.
- Agents can read it with the new read-only `digest` helper command. The first session each week mentions it once, with the number of suggestions.
- Nothing is applied by the digest. Every suggestion is a proposal. An agent applies one through a normal correction or forgetting only after the owner explicitly approves it. Requests name memories by ID only.
- The digest is built from records the viewer may already see. Live Home stays general-only by default; the owner view adds private records for the signed-in owner, and sensitive records are never included.

## Speed

Near-duplicate detection compares only memories that share one of their two rarest words. 5,000 synthetic memories take under 2 seconds. The weekly session-start mention costs about 0.35 seconds once a week at 3,000 memories. Other sessions only read a small marker file, and per-message recall is unchanged.

## Upgrade

Connected agents receive 2.7.0 through the normal compatible automatic update. No hook reinstall or Codex re-trust is needed. A Live Home host pinned to an earlier tag shows the digest card after it is re-pinned to v2.7.0 and restarted.

## Verification and boundaries

The unit suite (183 tests), seed validation and the static and Live Home Chromium checks passed locally with synthetic data. The GitHub matrix covers macOS and Linux on Python 3.10, 3.11 and 3.13 plus browser verification. No personal Brain was used or connected.
