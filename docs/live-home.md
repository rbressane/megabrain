# Live Home

Live Home is an optional owner-authenticated, read-only viewer for a normal phone or desktop browser. It is not a new authority, an agent gateway, or a memory-writing API. Git remains authoritative. Local snapshots and agent use work without the viewer, including offline.

**Deployment gate:** the implementation is a release candidate. No public host or owner URL has been configured by this product work. Synthetic local verification is not proof of an internet deployment. Do not claim it live until the deployment acceptance below passes on the approved host.

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

1. Select an always-on host and dedicated HTTPS origin, such as `https://brain.example.invalid`. An origin has no path, query, fragment or credentials. Set up DNS and a publicly trusted TLS certificate using the host's existing certificate process. Use an existing reverse proxy if available. Do not expose the unencrypted backend port.
2. Install an official stable MegaBrain tag containing Live Home after release. Never deploy a development branch to a personal Brain. Before release, use the candidate only with synthetic data on an explicitly approved test target.
3. Provision the dedicated read-only replica yourself with Git. It must have `origin/main` and no dirty files or local unique commits. The viewer fetches `main`, but **never checks out, resets, merges, rebases, commits or pushes**. Its original `HEAD` can remain behind; the view is built directly from the fetched commit.
4. Set the owner passphrase in a private interactive terminal running as the service account:

   ```sh
   megabrain live owner --auth-file /srv/megabrain-state/owner.json
   ```

   Input is hidden and never echoed. The command stores only a salted PBKDF2-SHA256 verifier (600,000 iterations), mode 0600, in a private directory. It refuses noninteractive input. Do not ask an agent to fill the passphrase. Rotation through the same command revokes all browser sessions on their next request.
5. Start the viewer behind an **existing HTTPS reverse proxy**:

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

Before calling the feature shipped or providing a personal browsing URL:

1. Record the approved host, URL, data-replica authorization and operator responsibility privately, never personal infrastructure details in the public product SOT.
2. Deploy the exact candidate/merge revision to an approved synthetic test target. Verify that the public HTTPS origin presents a valid certificate on a normal phone browser, and that the backend is not remotely reachable over HTTP.
3. Confirm unauthenticated HTML/API/source access reveals no Brain data. Sign in, browse on desktop and phone, inspect inert Markdown, sign out, use browser back, and confirm session rotation/restart revocation. Verify cache and security headers through the real proxy.
4. Push a synthetic correction from a separate agent and observe it automatically with query, selection and reading position retained. Interrupt Git and service access separately, check honest freshness, and restore them. Confirm a dirty replica is retained and not served.
5. Verify runtime identity using the deployment revision record plus authenticated snapshot `live.runtime_version`; verify `data.snapshot_commit` matches the committed synthetic repository state.
6. Publish only after exact-commit CI and the approved deployment checks pass. Connecting a real Brain is a separate explicit owner-authorized operator step, not part of development/testing. Never attach private content to product evidence.

Product gates: `python3 -m unittest discover -s tests -v`, seed validation, `python3 tests/browser_smoke.py`, and `python3 tests/live_browser_smoke.py`. Chrome tests use an isolated temporary profile and synthetic repositories. Their loopback HTTP evidence is not a substitute for the public TLS/phone/host acceptance above.
