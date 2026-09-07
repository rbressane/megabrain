# MegaBrain 2.5.0 release candidate

**Not published or deployed.** Public HTTPS/phone/host acceptance is pending an approved deployment target. Runtime protocol remains 2; no Brain migration is required.

## Optional read-only Live Home

- One owner-approved HTTPS URL can be opened from normal phone and desktop browsers. Agents on each configured OS account share the link; owner sign-in stays separate.
- The existing graph-first Home gains live committed-Git refresh, visible last-sync status, offline recovery, owner sign-in/sign-out and preserved browsing state.
- A dedicated read-only replica fetches without checkout, merge, rebase, reset, commit or push. Invalid, dirty or local-unique state is never repaired or served.
- The first viewer is general-only. Private/sensitive records, raw imports, policies, attachments and arbitrary repository files remain excluded. Sources are exact allowlisted committed Markdown served as inert text.
- Corrections and forgetting still go through agent review. There is no browser memory-write API.
- Owner authentication uses a private salted password verifier and short-lived in-memory sessions. HTTPS, secure cookies, same-origin checks, no-store responses and CSP hashes protect the web boundary. This is not an independent security certification.
- `megabrain open` uses the approved device link when configured. `megabrain open --local` retains offline local snapshots; `live unlink` restores that default without stopping the service.
- The core still requires only Python's standard library and Git and works without a service. The viewer is opt-in, operator-hosted, and pinned to its starting runtime until restarted.

See [Live Home setup, limitations and deployment acceptance](live-home.md). No personal Brain was used in development. Repository tests and isolated Chrome checks use synthetic data. Local loopback verification does not establish public HTTPS reachability or authorize connecting a personal replica.
