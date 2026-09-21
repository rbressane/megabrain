# MegaBrain 2.5.0

Optional read-only Live Home and truthful recall readiness. Runtime protocol remains 2; no Brain migration is required.

## Optional read-only Live Home

- One owner-approved HTTPS URL can be opened from normal phone and desktop browsers. Agents on each configured OS account share the link; owner sign-in stays separate.
- The graph-first Home gains live committed-Git refresh, visible last-sync status, offline recovery, owner sign-in/sign-out and preserved browsing state.
- A dedicated read-only replica fetches without checkout, merge, rebase, reset, commit or push. Invalid, dirty or local-unique state is never repaired or served.
- The viewer is general-only. Private/sensitive records, raw imports, policies, attachments and arbitrary repository files remain excluded.
- Corrections and forgetting still go through agent review. There is no browser memory-write API.
- Owner authentication uses a private salted password verifier and short-lived in-memory sessions. HTTPS, secure cookies, same-origin checks, no-store responses and CSP hashes protect the web boundary.
- `megabrain open` uses the approved device link when configured. `megabrain open --local` retains offline local snapshots; `live unlink` restores that default without stopping the service.

## Recall readiness

- `status` and `doctor` report storage, synchronization, private-recall and canonical-search readiness separately.
- Setup reports connection success without implying that every recall capability is available.
- Protocol-1 search and resource-read failures describe the required read migration accurately.
- Synthetic coverage includes private date recall in Portuguese and English, exact versus approximate dates, correction behavior, protocol compatibility and denied-context privacy.
- Hermes remains general-only because this release has no trusted Hermes recall adapter. Group, scheduled, delegated, unknown and spoofed contexts do not inherit owner privileges.

## Verification and boundaries

Local release verification passed 122 unit tests, seed validation, static Chrome checks and Live Home Chrome checks with synthetic data. The GitHub matrix covers macOS and Linux on Python 3.10, 3.11 and 3.13 plus browser verification.

The synthetic Live Home operator trial is closed. Phone sign-in, automatic correction and passphrase rotation are owner-confirmed. Reboot/uptime, remaining public-proxy checks and authenticated runtime/snapshot comparison remain deferred to usage, not passed. See the [runbook](live-home.md) and [attributed verification record](verification/live-home.md).

No personal Brain was used or connected. Publishing v2.5.0 does not authorize connecting a personal replica. Private Git is not encryption. Vault, sensitive synchronization, attested delivery and Hermes private provenance remain independently gated.
