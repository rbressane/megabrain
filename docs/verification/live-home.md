# Live Home candidate verification

Reconciled 8 September 2026 from the owner-supplied private operator handoff and explicit closeout instruction. The operator trial used candidate `50d543b28b828bd144f58a11cb98f0b008a9a420` in [PR #25](https://github.com/rbressane/megabrain/pull/25). No personal Brain was connected or used in testing. Private hostnames, account names, paths, service identifiers and operational logs are deliberately omitted.

**Disposition:** the synthetic operator trial is closed for product closeout. Remaining operational checks are **deferred to usage by owner decision**, not passed and not a request for another manual acceptance round. This replaces the earlier blanket requirement that every public-deployment check pass before merge/release consideration. Automated regressions, exact-commit CI, explicit merge/release authorization and all authentication/privacy boundaries remain required. The candidate is not merged or released; stable remains v2.4.0.

## Earlier local candidate verification

Verified 7 September 2026 using synthetic repositories and isolated Chrome profiles. These results are local candidate evidence, not public-proxy or physical-phone evidence.

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

## Synthetic operator trial evidence

The following is attributed to the supplied private handoff. The coding agent did not access the host, retrieve its private logs/verifier or repeat these checks during closeout. A reported pass is limited to the behavior described, not blanket public-deployment acceptance.

| Check | Disposition and provenance |
| --- | --- |
| Exact candidate checkout | **Passed, operator-reported inspection:** HEAD `50d543b28b828bd144f58a11cb98f0b008a9a420`, clean worktree. This proves checkout identity, not a fresh authenticated runtime/snapshot comparison. |
| Independent isolated-HOME unit suite | **Passed, operator-reported retained output:** 120 tests, OK, exit 0 on that exact candidate. Receipt and log remain private; not independently reread by the coding agent. |
| Viewer and Funnel configuration | **Passed, operator-reported inspection:** viewer active under a dedicated unprivileged OS account, RunAtLoad/KeepAlive, loopback `127.0.0.1:8765`, exact HTTPS origin and `--behind-proxy`, no `--local-http`; Funnel proxies only the intended HTTPS origin to that listener. Configuration is not proof of reboot recovery or indefinite uptime. |
| Unauthenticated `/login` reachability | **Passed, operator-reported HTTP 200:** endpoint reachable. This alone proves neither authenticated access, protected API/source denial, nor deployed revision. |
| Synthetic correction synchronization | **Passed, operator-reported:** a correction was published and fetched into a separate check replica. Authenticated snapshot-commit equality was not freshly compared. |
| Phone sign-in and Home | **Passed, owner-confirmed:** sign-in worked and Home loaded following instructions to use a normal phone browser on cellular without Tailscale. This is owner observation, not independently instrumented transport verification. |
| Automatic phone update | **Passed, owner-confirmed:** an already-open Home changed from the synthetic blue-notebook memory to the green-notebook correction without manual refresh. Retained query, selection and reading position were not explicitly checked. |
| Passphrase rotation | **Passed, owner-confirmed:** refreshing the old session required sign-in, the old passphrase failed, and the new passphrase loaded Home. This does not establish every logout, expiry or restart scenario. |
| Hosting plan | **Owner-confirmed:** non-commercial free Personal-plan use. No paid hosting or custom domain was requested; this is not an independent billing audit. |

### Deferred to usage by owner decision

- Full host/Tailscale reboot recovery, sleep/disk-unlock behavior and unattended uptime. An active supervised process is not a successful reboot rehearsal.
- Remaining real-proxy failure/recovery checks, phone query/selection/reading-position retention, dirty-replica behavior, and other runbook scenarios without explicit operator evidence.
- Full public TLS/header/cache and protected-route checks, inert-source behavior, logout/back-navigation/expiry/restart combinations and upstream abuse-control assessment not established by the handoff. Existing local automation covers a subset; it is not a substitute for public-proxy evidence.
- Fresh authenticated `live.runtime_version` and `data.snapshot_commit` comparison against the deployed runtime and synthetic Git state. Candidate checkout identity and endpoint reachability are not equivalent proof.

These are recorded usage risks, not failed tests or new manual closeout blockers. Handle issues through normal owner/operator workflows if encountered; do not reopen acceptance rounds merely to fill this list. The deferral does not disable a security control, authorize personal data or establish independent security certification, unlimited capacity or personal-data readiness.

## Coding closeout and remaining release requirements

No new product defect is established by the handoff. Closeout reconciles evidence and the owner decision, clarifies source-based candidate commands, and generalizes launchd supervision/recovery guidance. No runtime, protocol, UI, stable installation or deployed service is changed.

The operator-tested commit's [push CI](https://github.com/rbressane/megabrain/actions/runs/34169670311) and [PR CI](https://github.com/rbressane/megabrain/actions/runs/34169672619) each passed all seven jobs, freshly checked during closeout. These are exact-candidate checks, not checks on a later documentation commit or an eventual merge.

### Closeout automation, 8 September 2026

- `python3 -m unittest discover -s tests -v` with a temporary isolated HOME: **120 passed**, exit 0.
- Seed validation: **passed**, zero errors/warnings. Python syntax parsing, `git diff --check`, local Markdown file links and a scan excluding private handoff identifiers: **passed**.
- `python3 tests/browser_smoke.py`: **passed**, four synthetic desktop/mobile viewports with an isolated Chrome profile and temporary HOME.
- `python3 tests/live_browser_smoke.py`: **passed** in the documented normal environment, with synthetic repositories and its isolated Chrome profile; four viewports plus owner sessions, corrections, retained UI state and failure recovery.
- Two additional Live Chrome attempts with an overridden temporary HOME **timed out at CDP `Page.navigate`**. The documented command then passed without that HOME override. The cause is not established; these failed attempts are not passes. No runtime, assertion or timeout was changed to obtain the passing result.

These are automated local checks, not another manual acceptance round or a new public-proxy inspection. Exact closeout-head CI and the final readiness receipt are attached to [PR #25](https://github.com/rbressane/megabrain/pull/25) and the canonical SOT; the CI links above pin the earlier operator-tested candidate.

- **Merge consideration:** documentation/evidence reconciliation and green exact-head automated checks. The operator-test disposition is satisfied by the recorded passes and explicit owner deferrals; it does not grant merge authorization.
- **Release publication:** separate authorization, an approved merge, green exact-merge CI and tag/release identity verification remain required. These Git/release checks are not deferred to usage. No release was published during closeout.
- **Personal Brain:** remains disconnected. Connection requires a suitable stable release and a separately authorized operator step. Do not save the synthetic test URL as the owner's permanent Brain destination.

See [the runbook's reconciled acceptance disposition](../live-home.md#required-deployment-acceptance).
