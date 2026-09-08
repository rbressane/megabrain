# MegaBrain 2.5.0 release candidate

**Not merged or published.** The private operator handoff reports a running synthetic Mac/Funnel trial of `50d543b28b828bd144f58a11cb98f0b008a9a420`. Phone sign-in, automatic corrections and passphrase rotation are owner-confirmed. The owner closed the trial and deferred remaining operational checks to usage, not passed them. This supersedes the earlier blanket manual-deployment gate; it does not authorize merging, a release or personal-data connection. Runtime protocol remains 2; no Brain migration is required.

## Optional read-only Live Home

- One owner-approved HTTPS URL can be opened from normal phone and desktop browsers. Agents on each configured OS account share the link; owner sign-in stays separate.
- The existing graph-first Home gains live committed-Git refresh, visible last-sync status, offline recovery, owner sign-in/sign-out and preserved browsing state.
- A dedicated read-only replica fetches without checkout, merge, rebase, reset, commit or push. Invalid, dirty or local-unique state is never repaired or served.
- The first viewer is general-only. Private/sensitive records, raw imports, policies, attachments and arbitrary repository files remain excluded. Sources are exact allowlisted committed Markdown served as inert text.
- Corrections and forgetting still go through agent review. There is no browser memory-write API.
- Owner authentication uses a private salted password verifier and short-lived in-memory sessions. HTTPS, secure cookies, same-origin checks, no-store responses and CSP hashes protect the web boundary. This is not an independent security certification.
- `megabrain open` uses the approved device link when configured. `megabrain open --local` retains offline local snapshots; `live unlink` restores that default without stopping the service.
- The core still requires only Python's standard library and Git and works without a service. The viewer is opt-in, operator-hosted, and pinned to its starting runtime until restarted.

See [Live Home setup and reconciled acceptance disposition](live-home.md#required-deployment-acceptance) and the [attributed verification record](verification/live-home.md). No new product defect is established by the operator handoff; closeout changes documentation and generalized supervision/recovery guidance only. No personal Brain was used or connected. Local automation, operator inspection and owner phone observations are distinct evidence. Reboot/uptime, remaining real-proxy checks and authenticated runtime/snapshot comparison are usage follow-ups, not new manual gates. Automated regressions, exact-commit CI, separate merge/release authorization and release identity checks remain required. Stable remains v2.4.0.
