# Live Home candidate verification

Verified 7 September 2026 using synthetic repositories and isolated Chrome profiles. No personal Brain was read, copied, migrated or modified.

## Local gates

- `python3 -m unittest discover -s tests -v`: **120 tests passed**. Includes 15 Live Home tests covering protected routes, origin/host checks, form bounds, owner verifier permissions, rotation (including concurrent rotation during password work), expiry, logout, general-only filtering, committed corrections, invalid/unsafe state, offline recovery, no checkout/push and the installed link/local-open workflow.
- Seed validation: passed, zero errors and warnings.
- Python source compilation and `git diff --check`: passed.
- Existing static Home Chrome gate: passed at 1440×1000, 1920×800, 390×844 and 430×1100, including resources, review, inert text, handoffs and search.
- Live Home Chrome gate: passed at the same four viewport sizes. Exercised actual owner sign-in, HttpOnly sessions, automatic cross-agent corrections, retained query/focus, graph selection/zoom, open resource disclosure, inert Markdown, Git-offline recovery, dirty-clone fail-closed behavior, sign-out and back-navigation reauthentication.
- HTTP security tests passed again after the final authentication changes. Browser tests use the explicit loopback development transport. They do not prove public TLS or a physical phone deployment.
- The optional skill-creator validator could not run because its external PyYAML dependency is absent. No runtime dependency was added to satisfy that external tool.

## UI review

The inherited Graph First layout, typography, neutral surfaces, violet selection and mobile topic list were preserved. A persistent last-sync/scope strip and sign-out were added. The separate sign-in form contains no Brain preview. Review was performed inline because the harness has no subagent facility.

The mechanical detector ran once in degraded regex mode: its HTML/CSS parser modules are absent, so findings are an undercount, not an accessibility certification. Remaining flags mainly concern pre-existing token/type drift; new compact live-status text follows the incumbent metadata density and sign-in text uses a larger form-specific hierarchy. No global redesign or unrelated token cleanup was performed.

Measured new-state text/focus contrast against the surface: primary 16.90:1, secondary 9.66:1, focus 8.25:1 and warning 8.62:1. The sign-in field boundary was strengthened to 3.74:1 and confirmed in final desktop/mobile captures. No Lighthouse score or full assistive-technology certification is claimed.

UI disposition: **ship at the reviewed UI scope**, not deployment approval. Local screenshots are ignored verification artifacts under `.impeccable/review/live-*.png`; no raster assets or private evidence ship with the runtime.

## Remaining release gate

The owner approved free Tailscale Funnel transport for an operator-managed Mac. The narrow transport exception and setup runbook are recorded; no tunnel was activated. Actual host trust/access, free-plan eligibility, macOS variant compatibility and the exact public HTTPS origin remain unverified. Do not merge/publish the candidate as a completed Live Home shipment until the approved synthetic deployment acceptance in [the runbook](../live-home.md#required-deployment-acceptance) passes. The stable release remains 2.4.0. Public HTTPS, real phone access, supervision, exact deployed revision and any later explicitly authorized personal-replica connection remain unverified.
