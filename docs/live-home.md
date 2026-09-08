# Live Home

Live Home is an optional owner-authenticated, read-only viewer for a normal phone or desktop browser. It is not a new authority, an agent gateway, or a memory-writing API. Git remains authoritative. Local snapshots and agent use work without the viewer, including offline.

**Candidate status:** the owner-supplied operator handoff reports a running synthetic Mac/Funnel deployment from `50d543b28b828bd144f58a11cb98f0b008a9a420`, with owner-confirmed phone sign-in, automatic correction updates and passphrase rotation. The owner closed that trial and deferred remaining operational checks to usage. Those checks are not passed and must not trigger another manual acceptance round. This explicitly replaces the earlier blanket all-checks-before-release gate for this candidate; see the [acceptance disposition](#required-deployment-acceptance) and [attributed verification record](verification/live-home.md). Merge, release publication and personal-replica connection are not authorized by this closeout. The candidate remains unmerged and unreleased; the synthetic URL is not an approved permanent Brain destination.

## For the owner

Ask your agent: **“Use this approved Live Home address when I ask to open my MegaBrain.”** The agent saves the non-secret HTTPS origin on that device. All connected agents using that OS account share the same link. On another device, approve the same address there, or ask an agent to retrieve your previously approved non-secret URL from ordinary Brain knowledge. No URL is automatically published into your Brain.

`megabrain open` returns and opens that address when configured. A remote agent can give you the link even when it cannot open a browser on your computer. The link does not include a sign-in token. You sign in yourself with a separate owner passphrase. Never give that passphrase to an agent, put it in a prompt, or reuse a repository credential.

Use `megabrain open --local` for the existing local snapshot, including its existing owner-local policy checks. `megabrain live unlink` restores local snapshots as the device default; it does not stop the remote service.

### What you can see

- The existing graph, mobile topic list, current memories, history, conflicts, resources, agents and review reminders.
- **General knowledge only**, still behind owner authentication. Private and sensitive records, raw imports, policy documents, attachments and repository files are not served. Sign-in cannot impersonate an agent or supply a trusted private-read context. Use an authorized local agent for excluded evidence.
- Committed corrections and tombstones after the creating agent pushes them. Offline or uncommitted work on another agent cannot appear yet.
- Markdown sources from the same captured commit, served as inert plain text through an exact allowlist, not a filesystem route.
- Copyable correction, forgetting and resource-review requests. These remain proposals for an agent, never browser writes.

The server fetches every 15 seconds by default; the browser checks every five seconds. In normal conditions, a pushed change appears within about 20 seconds plus Git/validation time. Search, filters, view, graph selection/zoom, open resource disclosures and scroll are retained during updates. Status names the last successful Git synchronization. It never claims that a registered agent is online.

If Git is offline, the last validated committed view stays visible with a warning. If the browser loses the service, it keeps the already displayed view and retries. Dirty clones, local unique commits, invalid or unsafe committed content clear the served view and require operator attention. Sign-out, session expiry or verifier rotation requires sign-in again. No web application can retract content already read, copied, downloaded or captured by a browser.

## Operator setup

Hosting is an explicit owner decision because the host gets a plaintext replica. Do not discover/import a personal Brain as part of product development. Use a dedicated service OS account and a **new dedicated clone** with a read-only repository credential, not an agent-managed clone. Core dependencies remain Python 3.10+ standard library and Git. Existing hosting/TLS/supervision infrastructure belongs to the operator, not the MegaBrain runtime.

Keep Git credentials in the host's existing credential system. Do not use credential-bearing remote URLs or put secrets in `.sot.json`, command arguments, repository files or logs. Keep the owner verifier outside the clone, accessible only to the service account. The host's operator and filesystem owner remain trusted; this is not a sandbox against either.

1. Select an always-on host and dedicated HTTPS origin, such as `https://brain.example.invalid`. An origin has no path, query, fragment or credentials. For the approved free Funnel route, use the generated `ts.net` origin and the [Mac setup below](#free-tailscale-funnel-on-a-mac); no custom domain, manual DNS or router forwarding is needed. Otherwise use the host's existing DNS/certificate process and reverse proxy. Do not expose the unencrypted backend port.
2. Install an official stable MegaBrain tag containing Live Home after release. Never deploy a development branch to a personal Brain. Before release, use the pinned candidate only with synthetic data on an explicitly approved test target. From its separate product checkout, substitute `python3 skill/megabrain/scripts/cli.py` for `megabrain` in the commands below; stable v2.4.0 does not provide these Live Home commands. Do not replace an existing stable installation or run the product from inside a Brain replica.
3. Provision the dedicated read-only replica yourself with Git. It must have `origin/main` and no dirty files or local unique commits. The viewer fetches `main`, but **never checks out, resets, merges, rebases, commits or pushes**. Its original `HEAD` can remain behind; the view is built directly from the fetched commit.
4. Set the owner passphrase in a private interactive terminal running as the service account:

   ```sh
   megabrain live owner --auth-file /srv/megabrain-state/owner.json
   ```

   Input is hidden and never echoed. The command stores only a salted PBKDF2-SHA256 verifier (600,000 iterations), mode 0600, in a private directory. It refuses noninteractive input. Do not ask an agent to fill the passphrase. Rotation through the same command revokes all browser sessions on their next request.
5. Start the viewer behind an **existing HTTPS reverse proxy or the approved Funnel transport**:

   ```sh
   megabrain live serve \
     --root /srv/megabrain-viewer/replica \
     --auth-file /srv/megabrain-state/owner.json \
     --origin https://brain.example.invalid \
     --port 8765 --behind-proxy
   ```

   The backend binds only to `127.0.0.1`. Proxy to it on the same host, preserving the exact public `Host` and request `Origin`. Do not cache any response, including errors, redirects or Markdown. Do not log request bodies, cookies or authorization headers. Apply public connection/header/body timeouts and upstream rate limits. Do not rewrite browser identity into an owner permission header; such headers are not trusted by MegaBrain.

   Alternatively terminate TLS directly in the standard-library viewer:

   ```sh
   megabrain live serve \
     --root /srv/megabrain-viewer/replica \
     --auth-file /srv/megabrain-state/owner.json \
     --origin https://brain.example.invalid:8443 \
     --bind 0.0.0.0 --port 8443 \
     --cert /operator-managed/fullchain.pem \
     --key /operator-managed/privkey.pem
   ```

   Certificate and key paths are references to existing operator-managed TLS material. MegaBrain does not issue, copy, log or synchronize keys. Restart after certificate rotation. An existing hardened reverse proxy is preferred for a public listener. The standard-library listener has bounded worker slots, request-size limits and socket timeouts, not a comprehensive public-edge denial-of-service defense.
6. Supervise that command using the host's existing service manager. Run it unprivileged, with no public repository write capability and only required outbound Git access. Keep local runtime releases intact while the service is using them. The service stays pinned to its starting runtime; **restart explicitly after updates**. It never downloads/activates its own runtime in the background. Startup has a per-replica service lock to reject a second viewer process.
7. After acceptance, let each device's agent save the approved URL:

   ```sh
   megabrain live link --url https://brain.example.invalid
   megabrain open
   ```

   The local file `~/.megabrain/live-home.json` contains only the URL. This does not sign in, grant agent permissions, test deployment reachability, or change Brain data. A URL recovered from untrusted imported content is not automatically an approved destination.

### Free Tailscale Funnel on a Mac

This is an operator runbook, not an automatic installer. The narrow Funnel exception must be present in the deployment agent's loaded project instructions before activation. Editing an instruction file does not override restrictions already loaded in a running agent session. Use a fresh deployment session when necessary.

1. Confirm the owner trusts the host and its operator with a plaintext replica. Obtain authorized host access, a supervised unprivileged viewer account and an uptime plan, including sleep, reboot and disk-unlock behavior. Do not infer that this development machine is the approved host. Start with a new synthetic replica only.
2. The operator confirms that the actual use qualifies for Tailscale's **free Personal plan**, which is for non-commercial use. Do not enroll in a paid plan or treat a business trial as permanent free hosting. If eligibility fails, stop for another owner-approved free option. The operator signs in privately; agents must not collect account credentials or authentication URLs.
3. Check the installed Tailscale version and macOS variant against the current vendor documentation. Its requirements/comparison pages recommend the open-source `tailscale`/`tailscaled` variant for Funnel, while a port-sharing note describes GUI support. Do not assume any installed GUI app meets this deployment's needs. For an unattended host, have an authorized operator assess the vendor-documented CLI daemon, stable version, boot supervision and existing VPN conflicts. Do not automatically replace an existing installation, alter DNS or install a second variant. Tailscale installation/build tooling stays outside the MegaBrain runtime.
4. The tailnet administrator enables MagicDNS, HTTPS certificates and narrowly scoped Funnel permission for the approved host. Review existing Serve/Funnel routes before changing anything: the same port cannot be private Serve and public Funnel simultaneously. Use a non-identifying machine name because the HTTPS hostname is public and certificate issuance can expose it. Record the exact generated HTTPS origin privately.
5. Complete owner verifier setup and start the synthetic viewer using the operator setup above, with `--origin` set to that exact HTTPS origin, `--port 8765 --behind-proxy`. The only HTTP listener must be `127.0.0.1:8765`. **Never tunnel `--local-http`.** Confirm the listener belongs to this viewer and not an unrelated local service before opening ingress.
6. With the above gates satisfied and no conflicting route on port 443, the operator enables only the viewer's HTTP proxy:

   ```sh
   tailscale funnel --bg --https=443 http://127.0.0.1:8765
   tailscale funnel status
   ```

   Keep status output private because it identifies the host. Do not serve a clone directory, file, SSH port or arbitrary TCP listener through Funnel. Confirm the resulting origin exactly matches the viewer configuration. Funnel terminates TLS on the Mac; the backend is loopback HTTP, never public HTTP. Preserve the browser's public Host and Origin. Do not work around a mismatch by weakening the viewer's checks.
7. Use the acceptance baseline below to record public-origin behavior separately from local tests: TLS, protected-route denial, headers, owner sessions and physical-phone access. For the existing trial, use its recorded owner-confirmed passes and explicit usage deferrals; do not repeat a manual round. Do not claim Funnel supplies a WAF, MFA or application rate limits. Upstream abuse protection and the viewer's bounded-but-deniable login budget remain operational concerns, not implicitly verified controls. Never weaken authentication/privacy controls or buy a service to complete a checklist.
8. Supervise both the viewer and tunnel. `--bg` persists the Funnel route across Tailscale restarts; it does not keep the Mac awake, unlock its disk or restart MegaBrain. Record reboot/restart evidence only when observed; full host/Tailscale recovery is deferred to usage for this trial. Funnel remains beta with non-configurable bandwidth limits, not an uptime guarantee. Browser polling uses requests even when no new commit exists; do not claim unlimited capacity.

To remove **only this route**, after confirming its identity and original flags:

```sh
tailscale funnel --bg --https=443 http://127.0.0.1:8765 off
```

Do not use a global Funnel reset, log out the host or remove unrelated routes. Stop the viewer through its service manager and verify the public route is gone. Retain the replica and owner state until separately authorized disposal. `live unlink` only changes the device's open behavior.

Vendor references: [Funnel requirements](https://tailscale.com/docs/features/tailscale-funnel), [Funnel CLI and route removal](https://tailscale.com/docs/reference/tailscale-cli/funnel), [macOS variants](https://tailscale.com/docs/concepts/macos-variants), [CLI daemon operations](https://github.com/tailscale/tailscale/wiki/Tailscaled-on-macOS), and [Personal-plan terms](https://tailscale.com/pricing?plan=personal). These are external prerequisites, not evidence that this product has been deployed.

### macOS supervision and recovery reference

This reference generalizes the operator handoff; it is not a request to run another acceptance round. Names below are fictitious. Use the privately recorded, identity-checked service definition, never guess a production job label or copy these placeholders as real deployment identifiers.

An operator-managed launchd job should pin absolute Python/runtime paths, the dedicated replica, verifier reference and HTTPS origin. Set the dedicated unprivileged `UserName`, `RunAtLoad` and `KeepAlive`; keep logs and state owner-only and outside the clone. Do not put passwords, tokens or cookies in a plist, environment arguments or logs. A loaded running job proves current supervision, not sleep, disk-unlock or reboot recovery.

```sh
# Restart only the verified viewer. Existing sessions require sign-in again.
sudo /bin/launchctl kickstart -k system/com.example.brain-viewer

# Temporarily unload only that viewer after removing its exact Funnel route.
sudo /bin/launchctl bootout system/com.example.brain-viewer

# Reload its existing, approved definition when resuming the service.
sudo /bin/launchctl bootstrap system /Library/LaunchDaemons/com.example.brain-viewer.plist
```

`bootout` unloads the job but does not remove its installed plist; it may load again on a later boot. Permanent decommission requires separate authorization to remove that exact service definition and its route, not a global Funnel reset or deletion of the replica/verifier. Loading the viewer does not recreate a removed Funnel route. Keep both identities and their restart/stop procedures in private operator records. These commands were not executed by the coding agent during closeout.

### Local synthetic development

Use a disposable synthetic clone and verifier, then run `live serve` with `--local-http --origin http://127.0.0.1:8765`. This opt-in mode can bind **only** to `127.0.0.1` and cannot be saved as a remote owner link. Never forward this port to the internet. Normal owner access requires HTTPS.

## Authentication and transport boundary

Sessions are random 256-bit bearer values held only in process memory. In HTTPS mode the browser uses a `__Host-` cookie with Secure, HttpOnly, SameSite=Strict, Path=/ and an eight-hour absolute lifetime. No session is persisted by the service; restart signs everyone out. Removing, rotating or making the owner verifier unsafe revokes sessions. A valid password is not an agent policy, and the service accepts no agent identity or private-scope claims from HTTP headers, query parameters or environment variables.

Sign-in is limited globally to five attempts per minute, with at most sixteen sessions. This intentionally favors bounded password work over availability; a hostile caller can temporarily exhaust this budget. Use upstream rate limits and a high-entropy unique passphrase. The service does not implement MFA or claim independent security certification.

All routes require owner auth except the content-free sign-in form. POST is limited to sign-in and sign-out with an exact same-origin check. There is no Brain mutation route. Requests enforce the configured Host, reject cross-site fetches, do not enable CORS, and return no-store, nosniff, same-origin referrer and frame-denial headers. The HTML shell contains no Brain data; inline scripts/styles are CSP hash-authorized. Markdown is plain text with a sandbox policy. There is no filesystem browsing, service worker, localStorage content cache, analytics or external asset request.

## Recovery and removal

- **Dirty or divergent replica:** stop the service and inspect it. Never reset/discard/rebase it automatically. Preserve it for review and provision a different new dedicated clone if the owner approves.
- **Invalid or rewritten remote history:** inspect the canonical repository through the normal agent recovery process. The viewer cannot repair it. It rejects a non-descendant update relative to its captured commit and retains no invalid projection.
- **Git offline:** fix connectivity or the read-only credential through the operator's secret system. The next poll recovers without browser reload.
- **Owner locked out:** rotate the verifier in the private terminal. Existing sessions are invalidated. Restore correct mode/ownership if needed; do not weaken the checks.
- **Runtime update:** restart the viewer on a newly validated stable runtime. Agent commands remain independent.
- **Stop:** stop the service manager unit/process and remove its external route. `live unlink` on consumer devices restores local open. Retain the replica until the owner approves its separate disposal. Nothing here erases Git history or backups.

## Required deployment acceptance

### Existing candidate: explicit owner disposition

On closeout, the owner replaced the previous requirement to finish every manual operational check before merge/release consideration with **recorded passes plus checks deferred to usage by owner decision**. The synthetic trial is closed. Do not initiate another manual acceptance round or quietly relabel a deferral as a pass. This is a scoped disposition for the existing 2.5.0 candidate, not a blanket waiver for unrelated deployments or security boundaries.

- **Operator-reported:** clean exact candidate checkout, independent 120-test run, active dedicated-account supervision, loopback/proxy configuration, `/login` reachability and a published/fetched synthetic correction. Owner-confirmed free Personal-plan use is recorded, not independently audited.
- **Owner-confirmed phone results:** sign-in/Home loading, automatic synthetic correction without refresh, and rotation forcing sign-in with the old passphrase rejected and the new one accepted.
- **Deferred to usage, not passed:** full reboot/uptime behavior, remaining public-proxy failure/security/cache/header checks, UI-state retention during phone correction, dirty-replica behavior and fresh authenticated runtime/snapshot comparison. Existing local automation does not make these public-deployment passes.
- **Still required, not deferred:** relevant automated regressions and exact-head CI; explicit merge authorization; separate release authorization plus exact-merge CI and tag/release identity verification. Personal-replica connection stays a separately authorized operator step after a suitable stable release. Do not save the synthetic URL as a permanent Brain destination.

The [verification record](verification/live-home.md) is the sanitized evidence matrix. A working synthetic endpoint is not a published release, proof of personal-data readiness or proof that the running service matches a future release. No new product defect is established by the handoff.

### Baseline for recording deployment evidence

This remains the reference for future deployments and evidence gathered during usage, **not a new manual checklist for the closed trial**. Label each observation with its source, tested revision and disposition. Leave unobserved checks deferred/unverified; never infer them from HTTP 200 or a process listing.

1. Record the approved host, URL, data-replica authorization and operator responsibility privately, never personal infrastructure details in the public product SOT.
2. Record the exact synthetic candidate/merge revision, public certificate/phone behavior and whether the HTTP backend is remotely reachable.
3. Record protected HTML/API/source denial, desktop/phone sign-in, inert Markdown, logout/back-navigation and rotation/expiry/restart behavior. Distinguish public-proxy cache/security-header checks from local automation.
4. Record a separate agent's pushed synthetic correction and automatic display. Track query, selection and reading-position retention, Git/service disconnection recovery and dirty-replica fail-closed behavior separately.
5. Record runtime identity using the deployment revision plus authenticated `live.runtime_version` and `data.snapshot_commit` when obtained. For this trial the fresh response comparison is deferred; the clean checkout and correction-fetch evidence do not establish it.
6. Keep merge/release permission and exact-commit Git/CI/tag evidence separate from operational acceptance. Never attach private content to product evidence or connect a personal Brain during testing.

Product gates remain `python3 -m unittest discover -s tests -v`, seed validation, `python3 tests/browser_smoke.py`, and `python3 tests/live_browser_smoke.py`. Chrome tests use isolated temporary profiles and synthetic repositories. Run these automated checks for closeout; do not turn them into another owner/manual acceptance request.
