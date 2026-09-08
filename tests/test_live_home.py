"""Synthetic-only Live Home security, synchronization and installed command tests."""
from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.parse import urlencode
from unittest import mock

from tests.test_megabrain import BrainNetwork, run, SCRIPTS
import live_home
import cli
import operations


class OwnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "owner.json"
        self.password = "synthetic-only-owner-passphrase"
        operations.atomic_write(self.path, json.dumps(live_home.password_record(self.password)))
        self.auth = live_home.OwnerAuth(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_verifier_permissions_rotation_expiry_and_logout(self):
        self.assertNotIn(self.password, self.path.read_text())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        token = self.auth.login(self.password)
        self.assertTrue(self.auth.allowed(token))
        self.assertFalse(self.auth.allowed("synthetic-invalid-token"))
        with mock.patch.object(live_home.time, "monotonic", return_value=time.monotonic() + live_home.SESSION_SECONDS + 1):
            self.assertFalse(self.auth.allowed(token))
        token = self.auth.login(self.password)
        operations.atomic_write(self.path, json.dumps(live_home.password_record(self.password)))
        self.assertFalse(self.auth.allowed(token))
        token = self.auth.login(self.password)
        self.auth.logout(token)
        self.assertFalse(self.auth.allowed(token))
        token = self.auth.login(self.password)
        self.path.chmod(0o644)
        self.assertFalse(self.auth.allowed(token))
        with self.assertRaises(live_home.LiveError):
            live_home.read_owner(self.path)

    def test_rotation_during_password_work_cannot_grant_a_new_session(self):
        replacement = live_home.password_record("replacement-synthetic-passphrase")
        derive = live_home.hashlib.pbkdf2_hmac
        def rotate(*args):
            result = derive(*args)
            operations.atomic_write(self.path, json.dumps(replacement))
            return result
        with mock.patch.object(live_home.hashlib, "pbkdf2_hmac", side_effect=rotate):
            token = self.auth.login(self.password)
        self.assertFalse(self.auth.allowed(token))

    def test_rate_limit_and_missing_verifier_fail_closed(self):
        for _ in range(5):
            self.assertIsNone(self.auth.login("incorrect-synthetic-passphrase"))
        with self.assertRaises(live_home.LiveError):
            self.auth.login(self.password)
        self.path.unlink()
        self.assertFalse(self.auth.allowed("synthetic-session"))
        with self.assertRaises(live_home.LiveError):
            live_home.OwnerAuth(self.path)

    def test_symlink_and_invalid_owner_files(self):
        link = self.path.parent / "link"
        link.symlink_to(self.path)
        with self.assertRaises(live_home.LiveError):
            live_home.read_owner(link)
        operations.atomic_write(self.path, "[]")
        with self.assertRaises(live_home.LiveError):
            live_home.read_owner(self.path)


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.network = BrainNetwork()
        self.writer = self.network.clone("writer", "codex")
        self.memory = self.network.remember("writer", summary="Synthetic committed evidence.")
        self.root = self.network.clone("viewer")
        self.view = live_home.LiveView(self.root)

    def tearDown(self):
        self.network.close()

    def git(self, *args):
        return run(["git", *args], self.root).stdout.strip()

    def test_live_remote_changes_correction_and_no_checkout_or_push(self):
        original_head = self.git("rev-parse", "HEAD")
        self.view.refresh()
        first = self.view.data()
        self.assertTrue(first["available"])
        self.assertFalse(first["live"]["stale"])
        original = first["data"]["memories"][0]
        self.network.command("writer", "correct", {
            "summary": "Synthetic corrected evidence.",
            "source": {"type": "user-statement"},
        }, original["id"], "--stdin")
        remote_before = run(["git", "rev-parse", "main"], self.network.remote).stdout.strip()
        self.view.refresh()
        second = self.view.data()
        self.assertNotEqual(first["data"]["snapshot_commit"], second["data"]["snapshot_commit"])
        self.assertEqual(self.git("rev-parse", "HEAD"), original_head)
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(run(["git", "rev-parse", "main"], self.network.remote).stdout.strip(), remote_before)
        self.assertEqual([item["summary"] for item in second["data"]["memories"] if item["status"] == "current"], ["Synthetic corrected evidence."])
        self.assertIn(b"Synthetic committed evidence.", self.view.document(original["path"]))

    def test_offline_last_commit_dirty_and_recovery(self):
        self.view.refresh()
        previous = self.view.data()
        self.git("remote", "set-url", "origin", str(self.network.root / "missing.git"))
        self.view.refresh()
        offline = self.view.data()
        self.assertTrue(offline["available"])
        self.assertTrue(offline["live"]["stale"])
        self.assertEqual(previous["live"]["last_synced_at"], offline["live"]["last_synced_at"])
        self.assertEqual(previous["data"], offline["data"])
        dirty = self.root / "uncommitted.txt"
        dirty.write_text("Synthetic dirty content must never be served.")
        self.view.refresh()
        self.assertFalse(self.view.data()["available"])
        self.assertTrue(dirty.exists())
        self.assertIsNone(self.view.document(previous["data"]["memories"][0]["path"]))
        dirty.unlink()  # Test fixture only, never product recovery.
        self.git("remote", "set-url", "origin", str(self.network.remote))
        self.view.refresh()
        self.assertTrue(self.view.data()["available"])

    def test_private_sensitive_untracked_and_repository_files_not_served(self):
        self.network.remember("writer", subject="synthetic.private", summary="Synthetic private evidence.", sensitivity="private")
        self.network.remember("writer", subject="synthetic.sensitive", summary="Synthetic sensitive pointer.", sensitivity="sensitive")
        self.view.refresh()
        value = self.view.data()
        self.assertTrue(value["available"])
        serialized = json.dumps(value)
        self.assertNotIn("Synthetic private evidence.", serialized)
        self.assertNotIn("Synthetic sensitive pointer.", serialized)
        self.assertEqual(value["data"]["imports"], [])
        for path in (".git/config", "../../etc/passwd", "megabrain.json", "brain/policies/.gitkeep"):
            self.assertIsNone(self.view.document(path))
        for record in self.view.projection.documents.values():
            self.assertNotIn(b"Synthetic private evidence.", record)
            self.assertNotIn(b"Synthetic sensitive pointer.", record)

    def test_invalid_committed_tree_clears_previous_projection(self):
        self.view.refresh()
        run(["git", "config", "user.name", "Synthetic"], self.writer)
        run(["git", "config", "user.email", "synthetic@example.invalid"], self.writer)
        path = next((self.writer / "brain/memories").glob("*/*/*.md")).parent / "invalid.md"
        path.write_text("not a valid memory")
        run(["git", "add", str(path.relative_to(self.writer))], self.writer)
        run(["git", "commit", "-m", "synthetic invalid fixture"], self.writer)
        run(["git", "push"], self.writer)
        self.view.refresh()
        self.assertFalse(self.view.data()["available"])
        self.assertNotIn("invalid.md", json.dumps(self.view.data()))

    def test_local_unique_commits_not_rebased_or_pushed(self):
        self.git("commit", "--allow-empty", "-m", "synthetic local commit")
        head = self.git("rev-parse", "HEAD")
        self.view.refresh()
        self.assertFalse(self.view.data()["available"])
        self.assertEqual(self.git("rev-parse", "HEAD"), head)

    def test_unsafe_symlink_in_committed_source_fails_closed(self):
        self.view.refresh()
        (self.writer / "brain" / "synthetic-link").symlink_to("/etc/passwd")
        run(["git", "add", "brain/synthetic-link"], self.writer)
        run(["git", "commit", "-m", "synthetic unsafe mode"], self.writer)
        run(["git", "push"], self.writer)
        self.view.refresh()
        self.assertFalse(self.view.data()["available"])

    def test_installed_link_open_without_brain_and_local_fallback(self):
        home = self.network.homes["writer"]
        command = home / ".local/bin/megabrain"
        run([str(command), "live", "link", "--url", "https://brain.example.invalid"], self.root, env={"HOME": str(home)})
        linked = run([str(command), "open", "--no-open"], self.root, env={"HOME": str(home)})
        self.assertIn("https://brain.example.invalid", linked.stdout)
        self.assertIn("Owner sign-in required", linked.stdout)
        local = run([str(command), "open", "--local", "--no-open"], self.root, env={"HOME": str(home)})
        self.assertIn("Snapshot refreshed", local.stdout)
        run([str(command), "live", "unlink"], self.root, env={"HOME": str(home)})
        self.assertIsNone(live_home.saved_url(home))


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.password = "synthetic-browser-owner-passphrase"
        auth_path = root / "owner.json"
        operations.atomic_write(auth_path, json.dumps(live_home.password_record(self.password)))
        self.view = live_home.LiveView(root)
        self.view.projection = live_home.Projection("synthetic", {"synthetic": "Synthetic visible evidence"},
                                                    {"brain/memories/synthetic.md": b"<script>synthetic()</script>"})
        self.server = live_home.LiveServer(("127.0.0.1", 0), self.view, live_home.OwnerAuth(auth_path),
                                           "https://brain.example.invalid")
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=5)
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        client.request(method, path, body=body, headers={"Host": self.server.authority, **(headers or {})})
        response = client.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        client.close()
        return result

    def login(self):
        status, headers, body = self.request("POST", "/login", urlencode({"password": self.password}),
            {"Content-Type": "application/x-www-form-urlencoded", "Origin": self.server.origin})
        self.assertEqual(status, 303)
        self.assertNotIn(self.password.encode(), body)
        cookie = headers["Set-Cookie"]
        for flag in ("Secure", "HttpOnly", "SameSite=Strict", "Path=/", "__Host-"):
            self.assertIn(flag, cookie)
        return {"Cookie": cookie.split(";", 1)[0]}

    def test_authentication_every_route_no_data_in_shell_and_inert_source(self):
        status, _, body = self.request("GET", "/")
        self.assertEqual(status, 303)
        self.assertNotIn(b"Synthetic visible evidence", body)
        for route in ("/api/snapshot", "/source?path=brain/memories/synthetic.md", "/.git/config"):
            self.assertEqual(self.request("GET", route)[0], 401)
        headers = self.login()
        status, response_headers, body = self.request("GET", "/", headers=headers)
        self.assertEqual(status, 200)
        self.assertNotIn(b"Synthetic visible evidence", body)
        self.assertIn("sha256-", response_headers["Content-Security-Policy"])
        self.assertNotIn("unsafe-inline", response_headers["Content-Security-Policy"])
        status, response_headers, body = self.request("GET", "/api/snapshot", headers=headers)
        self.assertEqual(status, 200)
        self.assertIn(b"Synthetic visible evidence", body)
        self.assertIn("no-store", response_headers["Cache-Control"])
        self.assertNotIn("Access-Control-Allow-Origin", response_headers)
        status, response_headers, body = self.request("GET", "/source?path=brain/memories/synthetic.md", headers=headers)
        self.assertEqual(status, 200)
        self.assertTrue(response_headers["Content-Type"].startswith("text/plain"))
        self.assertIn("sandbox", response_headers["Content-Security-Policy"])
        self.assertEqual(response_headers["X-Content-Type-Options"], "nosniff")
        for route in ("/.git/config", "/source?path=../../etc/passwd", "/source?path=brain/private.md", "/source?path=x&path=y"):
            self.assertEqual(self.request("GET", route, headers=headers)[0], 404)
        self.assertEqual(self.request("POST", "/logout", headers={**headers, "Origin": self.server.origin})[0], 303)
        self.assertEqual(self.request("GET", "/api/snapshot", headers=headers)[0], 401)

    def test_forged_identity_csrf_host_and_methods_rejected(self):
        self.assertEqual(self.request("GET", "/api/snapshot", headers={"X-Owner": "true", "X-Forwarded-User": "owner"})[0], 401)
        self.assertEqual(self.request("GET", "/login", headers={"Host": "evil.example.invalid"})[0], 403)
        self.assertEqual(self.request("GET", "/login", headers={"Sec-Fetch-Site": "cross-site"})[0], 403)
        for origin in (None, "https://evil.example.invalid", "null"):
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            if origin:
                headers["Origin"] = origin
            self.assertEqual(self.request("POST", "/login", urlencode({"password": self.password}), headers)[0], 403)
        headers = self.login()
        for route in ("/remember", "/forget", "/api/snapshot"):
            self.assertEqual(self.request("POST", route, headers={**headers, "Origin": self.server.origin})[0], 405)
        for method in ("PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
            status, response_headers, body = self.request(method, "/api/snapshot", headers=headers)
            self.assertEqual(status, 501)
            self.assertIn("no-store", response_headers["Cache-Control"])
            self.assertNotIn(b"Synthetic visible evidence", body)

    def test_bad_password_and_form_bounds(self):
        headers = {"Content-Type": "application/x-www-form-urlencoded", "Origin": self.server.origin}
        status, _, body = self.request("POST", "/login", "password=wrong", headers)
        self.assertEqual(status, 401)
        self.assertIn(b"Sign-in failed", body)
        self.assertNotIn(b"value=\"wrong\"", body)
        for value in ("", "password=" + "a" * 5000, "password=a&password=b", "other=value"):
            self.assertEqual(self.request("POST", "/login", value, headers)[0], 400)


class ConfigurationTests(unittest.TestCase):
    def test_origin_validation_and_transport_gates(self):
        for value in ("http://brain.example.invalid", "https://owner:password@brain.example.invalid",
                      "https://brain.example.invalid/path", "https://brain.example.invalid?token=value",
                      "https://brain.example.invalid#value", "https://brain.example.invalid\n", "https://brain.example.invalid:99999"):
            with self.assertRaises(live_home.LiveError, msg=value):
                live_home.origin_url(value)
        self.assertEqual(live_home.origin_url("https://brain.example.invalid/"), "https://brain.example.invalid")
        self.assertEqual(live_home.origin_url("https://brain.example.invalid:443/"), "https://brain.example.invalid")
        parser = cli.build_parser()
        for transport in ("--local-http", "--behind-proxy"):
            args = parser.parse_args(["live", "serve", "--root", "/synthetic", "--auth-file", "/synthetic-owner",
                "--origin", "https://brain.example.invalid", "--bind", "0.0.0.0", transport])
            with self.assertRaises(live_home.LiveError):
                live_home.command(args)
        with mock.patch.object(os, "isatty", return_value=False):
            with self.assertRaises(live_home.LiveError):
                live_home.command(argparse.Namespace(live_action="owner"))


if __name__ == "__main__":
    unittest.main()
