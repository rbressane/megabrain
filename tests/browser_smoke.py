#!/usr/bin/env python3
"""Real Chrome smoke tests. Standard library only, isolated profile and synthetic Brain.

Run explicitly with CHROME=/path/to/chrome python3 tests/browser_smoke.py.
No browser installation, server, or personal browser profile is used.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.test_megabrain import BrainNetwork  # noqa: E402
from tests.test_canonical import canonical_local  # noqa: E402
import canonical  # noqa: E402


class CDP:
    def __init__(self, url):
        parsed = urllib.parse.urlsplit(url)
        self.socket = socket.create_connection((parsed.hostname, parsed.port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        self.socket.sendall((f"GET {parsed.path} HTTP/1.1\r\nHost: {parsed.hostname}:{parsed.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        header = b""
        while not header.endswith(b"\r\n\r\n"):
            header += self.socket.recv(1)
        expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        if header.split(b"\r\n", 1)[0].split()[1] != b"101" or expected not in header:
            raise RuntimeError("Chrome debugging handshake failed")
        self.sequence, self.session, self.errors = 0, None, []

    def exact(self, size):
        result = b""
        while len(result) < size:
            part = self.socket.recv(size - len(result))
            if not part:
                raise RuntimeError("Chrome debugging connection closed")
            result += part
        return result

    def send(self, value):
        body = json.dumps(value).encode()
        mask = os.urandom(4)
        size = len(body)
        length = bytes([0x80 | size]) if size < 126 else (bytes([0x80 | 126]) + struct.pack("!H", size) if size < 65536 else bytes([0x80 | 127]) + struct.pack("!Q", size))
        self.socket.sendall(b"\x81" + length + mask + bytes(byte ^ mask[index % 4] for index, byte in enumerate(body)))

    def receive(self):
        chunks = []
        while True:
            first, second = self.exact(2)
            size = second & 127
            if size == 126:
                size = struct.unpack("!H", self.exact(2))[0]
            elif size == 127:
                size = struct.unpack("!Q", self.exact(8))[0]
            if size > 32 * 1024 * 1024:
                raise RuntimeError("Chrome response exceeds smoke-test limit")
            mask = self.exact(4) if second & 128 else None
            body = self.exact(size)
            if mask:
                body = bytes(byte ^ mask[index % 4] for index, byte in enumerate(body))
            if first & 15 == 8:
                raise RuntimeError("Chrome debugging connection closed")
            chunks.append(body)
            if first & 128:
                return json.loads(b"".join(chunks))

    def call(self, method, **params):
        self.sequence += 1
        request = {"id": self.sequence, "method": method, "params": params}
        if self.session:
            request["sessionId"] = self.session
        self.send(request)
        while True:
            response = self.receive()
            if response.get("method") == "Runtime.exceptionThrown":
                self.errors.append(response["params"])
            if response.get("id") == self.sequence:
                if "error" in response:
                    raise RuntimeError(f"Chrome rejected {method}")
                return response.get("result", {})

    def evaluate(self, expression):
        result = self.call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in result:
            raise RuntimeError("Browser script failed: " + json.dumps(result["exceptionDetails"]))
        return result["result"].get("value")


def main():
    chrome = os.environ.get("CHROME") or shutil.which("google-chrome") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if not Path(chrome).is_file():
        raise SystemExit("Chrome is required for this explicit browser gate; set CHROME to its executable.")
    output = ROOT / ".impeccable/review"
    output.mkdir(parents=True, exist_ok=True)
    network = BrainNetwork()
    process = None
    profile = None
    try:
        root = network.clone("browser", "codex")
        for number, (subject, summary, confidence) in enumerate([
            ("gateway.recovery", "Recover the synthetic gateway from a verified snapshot, then check health.", "confirmed"),
            ("gateway.update", "Synthetic fleet updates require a dry run and a rollback checkpoint.", "inferred"),
            ("work.reporting", "Weekly synthetic reports put decisions and next actions first.", "confirmed"),
        ]):
            network.remember("browser", subject=subject, summary=summary, tags=[subject.split(".")[0]], confidence=confidence,
                             authority_domain="synthetic-project", review_after="2020-01-01T00:00:00Z" if number == 1 else None)
        body = "# Recovery\n\nConfirm the synthetic snapshot before restarting.\n\n## Verification\n\nCheck the synthetic health probe and keep the previous snapshot.\n<script>window.syntheticInjection=true</script>"
        canonical_local.create_or_revise_resource(root, {
            "resource_type": "runbook", "title": "Synthetic gateway recovery", "owner": "synthetic-owner",
            "authority_domain": "synthetic-project", "sensitivity": "general", "source_at": "2020-01-01T00:00:00Z",
            "verified_at": "2020-01-01T00:00:00Z", "freshness_at": None,
            "source": {"type": "user-statement", "locator": "synthetic://recovery", "fingerprint": canonical.content_fingerprint(body)}, "body": body,
        }, trusted_local=True)
        browsed = network.command("browser", "browse", None, "--no-open")
        with tempfile.TemporaryDirectory(prefix="megabrain-chrome-", ignore_cleanup_errors=True) as profile:
            process = subprocess.Popen([chrome, "--headless", "--no-first-run", "--no-default-browser-check",
                "--disable-background-networking", "--disable-component-update", "--disable-sync", "--disable-extensions",
                "--remote-debugging-port=0", "--user-data-dir=" + profile, "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
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
            cdp.call("Page.enable")
            cdp.call("Runtime.enable")
            cdp.call("Page.navigate", url=Path(browsed["path"]).as_uri())
            deadline = time.monotonic() + 10
            while not cdp.evaluate("document.readyState === 'complete' && !!document.querySelector('#brain-graph')"):
                if time.monotonic() > deadline:
                    raise RuntimeError("Synthetic Home did not render")
                time.sleep(0.1)
            for name, width, height in [("desktop", 1440, 1000), ("wide", 1920, 800), ("mobile", 390, 844), ("tall", 430, 1100)]:
                cdp.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=width < 760)
                cdp.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
                for view in ("overview", "resources", "review"):
                    cdp.evaluate(f"document.querySelector('[data-view={view}]').click()")
                    assert cdp.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Horizontal overflow: {name}/{view}"
                    assert cdp.evaluate("!window.syntheticInjection"), "Resource instructions executed"
                    screenshot = cdp.call("Page.captureScreenshot", format="png")["data"]
                    filename = f"{name}.png" if view == "overview" else f"{name}-{view}.png"
                    (output / filename).write_bytes(base64.b64decode(screenshot))
                cdp.evaluate("document.querySelector('[data-handoff]').click()")
                (output / f"{name}-handoff.png").write_bytes(base64.b64decode(cdp.call("Page.captureScreenshot", format="png")["data"]))
                assert cdp.evaluate("!document.getElementById('handoff-panel').hidden && document.getElementById('handoff-text').value.includes('confirmation')")
                cdp.evaluate("document.getElementById('dismiss-handoff').click()")
                assert cdp.evaluate("document.getElementById('handoff-panel').hidden")
                cdp.evaluate("document.querySelector('[data-view=resources]').click(); document.querySelector('.resource-card summary').click()")
                assert cdp.evaluate("document.querySelector('.resource-card details').open && !window.syntheticInjection")
                (output / f"{name}-resource-body.png").write_bytes(base64.b64decode(cdp.call("Page.captureScreenshot", format="png")["data"]))
                cdp.evaluate("document.querySelector('[data-view=explore]').click(); var field = document.getElementById('search'); field.value = 'no synthetic match'; field.dispatchEvent(new Event('input'))")
                assert cdp.evaluate("!!document.querySelector('.empty-state')")
            assert not cdp.errors, "Browser emitted runtime errors"
            print(json.dumps({"ok": True, "synthetic": True, "viewports": 4, "views_per_viewport": 3,
                              "checks": ["render", "overflow", "inert resource text", "handoff", "dismiss", "empty search", "reduced motion"],
                              "screenshots": ".impeccable/review"}, indent=2))
            cdp.socket.close()
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=10)
            process = None
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        if profile:
            shutil.rmtree(profile, ignore_errors=True)
        network.close()


if __name__ == "__main__":
    main()
