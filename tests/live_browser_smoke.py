#!/usr/bin/env python3
"""Real Chrome + HTTP lifecycle gate using isolated synthetic data only.

Loopback HTTP deliberately exercises the explicit development transport. Public
TLS, DNS and service supervision must additionally be verified on the chosen host.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.browser_smoke import CDP
from tests.test_megabrain import BrainNetwork, run
from tests.test_canonical import canonical_local, CanonicalRepositoryTests
import live_home
import operations


def wait(cdp, expression, seconds=40):
    deadline = time.monotonic() + seconds
    while not cdp.evaluate(expression):
        if time.monotonic() > deadline:
            diagnostic = cdp.evaluate("({path: location.pathname, title: document.title, text: document.body?.innerText.slice(0, 900)})")
            raise RuntimeError("Live browser acceptance timed out: " + expression + "\n" + json.dumps(diagnostic) + "\n" + json.dumps(cdp.errors))
        time.sleep(0.2)


def main():
    chrome = os.environ.get("CHROME") or shutil.which("google-chrome") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if not Path(chrome).is_file():
        raise SystemExit("Chrome is required for this explicit browser gate.")
    output = ROOT / ".impeccable/review"
    output.mkdir(parents=True, exist_ok=True)
    network = BrainNetwork()
    process = server = worker = refresher = cdp = None
    try:
        writer = network.clone("writer", "codex")
        for subject, summary in [("gateway.recovery", "Synthetic recovery starts with a verified snapshot."),
                                 ("gateway.updates", "Synthetic updates require a dry run and rollback checkpoint."),
                                 ("reporting.weekly", "Synthetic reports put decisions and next actions first.")]:
            network.remember("writer", subject=subject, summary=summary, tags=[subject.split(".")[0]], authority_domain="synthetic-project")
        resource = CanonicalRepositoryTests.resource_payload(None)
        resource["sensitivity"] = "general"
        canonical_local.create_or_revise_resource(writer, resource, trusted_local=True)
        root = network.clone("viewer")
        auth_file = network.root / "owner.json"
        password = "synthetic-browser-passphrase-only"
        operations.atomic_write(auth_file, json.dumps(live_home.password_record(password)))
        view = live_home.LiveView(root, interval=10)
        server = live_home.LiveServer(("127.0.0.1", 0), view, live_home.OwnerAuth(auth_file),
                                      "http://127.0.0.1:8765", local_http=True)
        origin = f"http://127.0.0.1:{server.server_port}"
        server.origin, server.authority = origin, f"127.0.0.1:{server.server_port}"
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        refresher = threading.Thread(target=view.run, daemon=True)
        worker.start(); refresher.start()
        with tempfile.TemporaryDirectory(prefix="megabrain-live-chrome-", ignore_cleanup_errors=True) as profile:
            process = subprocess.Popen([chrome, "--headless", "--no-first-run", "--no-default-browser-check",
                "--disable-background-networking", "--disable-component-update", "--disable-sync", "--disable-extensions",
                "--remote-debugging-port=0", "--user-data-dir=" + profile, "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            active = Path(profile) / "DevToolsActivePort"
            deadline = time.monotonic() + 20
            while not active.exists():
                if time.monotonic() > deadline:
                    raise RuntimeError("Chrome did not become ready")
                time.sleep(0.1)
            port = active.read_text().splitlines()[0]
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=5) as response:
                cdp = CDP(json.load(response)["webSocketDebuggerUrl"])
            target = cdp.call("Target.createTarget", url="about:blank")["targetId"]
            cdp.session = cdp.call("Target.attachToTarget", targetId=target, flatten=True)["sessionId"]
            cdp.call("Page.enable"); cdp.call("Runtime.enable")
            cdp.call("Page.navigate", url=origin)
            wait(cdp, "location.pathname === '/login' && !!document.querySelector('#password')")
            for name, width, height in [("desktop", 1440, 1000), ("mobile", 390, 844)]:
                cdp.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=width < 760)
                assert cdp.evaluate("document.documentElement.scrollWidth <= innerWidth")
                (output / f"live-login-{name}.png").write_bytes(base64.b64decode(cdp.call("Page.captureScreenshot", format="png")["data"]))
            cdp.evaluate(f"document.getElementById('password').value = {json.dumps(password)}; document.querySelector('form').requestSubmit()")
            wait(cdp, "location.pathname === '/' && !!document.querySelector('#brain-graph')")
            assert cdp.evaluate("!document.cookie.includes('megabrain')"), "Session cookie is not HttpOnly"
            assert cdp.evaluate("!document.querySelector('#live-bar').hidden && document.querySelector('#live-status').textContent.includes('Read-only')")
            for name, width, height in [("desktop", 1440, 1000), ("wide", 1920, 800), ("mobile", 390, 844), ("tall", 430, 1100)]:
                cdp.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=width < 760)
                cdp.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
                cdp.evaluate("document.querySelector('[data-view=overview]').click(); window.scrollTo(0, 0)")
                assert cdp.evaluate("document.documentElement.scrollWidth <= innerWidth"), name
                assert cdp.evaluate("getComputedStyle(document.querySelector('#live-detail')).display !== 'none'")
                (output / f"live-{name}.png").write_bytes(base64.b64decode(cdp.call("Page.captureScreenshot", format="png")["data"]))
            cdp.evaluate("document.querySelector('[data-view=resources]').click(); document.querySelector('details').open = true; window.scrollTo(0, 0)")
            resource_uri = cdp.evaluate("document.querySelector('[data-resource]').dataset.resource")
            resource_commit = cdp.evaluate("DATA.snapshot_commit")
            network.remember("writer", subject="synthetic.new-resource-check", summary="Synthetic background change.", tags=["gateway"])
            wait(cdp, f"DATA.snapshot_commit !== {json.dumps(resource_commit)}")
            assert cdp.evaluate(f"state.view === 'resources' && document.querySelector('[data-resource]').dataset.resource === {json.dumps(resource_uri)} && document.querySelector('details').open")
            cdp.evaluate("document.querySelector('[data-view=overview]').click(); selectGraphNode('topic:gateway', 'mobile'); state.graphScale = 1.3")
            original = cdp.evaluate("DATA.memories.find(item => item.subject === 'gateway.recovery').id")
            network.command("writer", "correct", {"summary": "Synthetic corrected recovery evidence.", "source": {"type": "user-statement"}}, original, "--stdin")
            wait(cdp, "DATA.memories.some(item => item.summary === 'Synthetic corrected recovery evidence.' && item.status === 'current')")
            assert cdp.evaluate("state.graphSelected === 'topic:gateway' && state.graphScale === 1.3")
            cdp.evaluate("(async () => { document.querySelector('[data-view=explore]').click(); await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))); const search = document.getElementById('search'); search.value='Synthetic corrected'; search.dispatchEvent(new Event('input')); search.focus(); })()")
            current = cdp.evaluate("DATA.snapshot_commit")
            network.remember("writer", subject="synthetic.latest", summary="Synthetic corrected matching addition.")
            wait(cdp, f"DATA.snapshot_commit !== {json.dumps(current)}")
            assert cdp.evaluate("state.query === 'Synthetic corrected' && document.activeElement.id === 'search' && document.querySelectorAll('.memory-card').length === 2")
            assert cdp.evaluate("(async () => { const link = document.querySelector('.memory-card a'); const response = await fetch(link.href); return response.ok && response.headers.get('Content-Type').startsWith('text/plain'); })()")
            run(["git", "remote", "set-url", "origin", str(network.root / "missing.git")], root)
            wait(cdp, "document.getElementById('live-status').textContent.includes('Git is unreachable')")
            assert cdp.evaluate("document.querySelectorAll('.memory-card').length === 2")
            run(["git", "remote", "set-url", "origin", str(network.remote)], root)
            wait(cdp, "document.getElementById('live-status').textContent.includes('Read-only')")
            dirty = root / "synthetic-dirty.txt"
            dirty.write_text("Synthetic dirty fixture.")
            wait(cdp, "document.getElementById('live-status').textContent.includes('needs attention')")
            assert cdp.evaluate("document.querySelectorAll('.memory-card').length === 0 && DATA.memories.length === 0")
            assert dirty.exists()
            dirty.unlink()  # Test-fixture cleanup, never product recovery.
            wait(cdp, "document.getElementById('live-status').textContent.includes('Read-only')")
            cdp.evaluate("document.querySelector('#live-bar form').requestSubmit()")
            wait(cdp, "location.pathname === '/login' && !!document.querySelector('#password')")
            assert cdp.evaluate("(async () => (await fetch('/api/snapshot')).status === 401)()")
            cdp.evaluate("history.back()")
            wait(cdp, "location.pathname === '/login' && !!document.querySelector('#password')")
            assert not cdp.errors, "Browser emitted runtime errors"
            print(json.dumps({"ok": True, "synthetic": True, "transport": "loopback development HTTP",
                "viewports": 4, "checks": ["owner sign-in", "HttpOnly", "responsive status", "resource disclosure retained",
                "cross-agent correction", "graph selection and zoom retained", "search and focus retained", "inert source route",
                "offline recovery", "dirty clone fail-closed", "sign-out", "back navigation reauthentication"],
                "screenshots": ".impeccable/review/live-*.png"}, indent=2))
    finally:
        if cdp:
            cdp.socket.close()
        if process:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        if server:
            server.view.stop.set()
            server.shutdown(); server.server_close()
        if worker:
            worker.join(timeout=5)
        if refresher:
            refresher.join(timeout=30)
        network.close()


if __name__ == "__main__":
    main()
