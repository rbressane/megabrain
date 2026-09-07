"""Synthetic daily updater acceptance. No personal installations or network services."""
from __future__ import annotations

import argparse
import concurrent.futures
from datetime import datetime, timedelta, timezone
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from tests import test_megabrain as fixtures
import bootstrap
import operations
import updates


class UpdateScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        self.runtime = {"version": "2.4.0", "automatic_updates": True, "source": str(self.home / "offline.git")}
        bootstrap.save_config(self.home, {"schema": bootstrap.CONFIG_SCHEMA, "runtime": self.runtime, "clones": {}})
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def tearDown(self):
        self.temporary.cleanup()

    def test_daily_schedule_backoff_clock_changes_and_legacy_state(self):
        self.assertIsNone(updates.due(self.runtime, {}, self.now))
        old = {"status": "updated", "checked_at": updates.stamp(self.now)}
        self.assertEqual(updates.due(self.runtime, old, self.now + timedelta(hours=23)), "check_not_due")
        self.assertIsNone(updates.due(self.runtime, old, self.now + timedelta(hours=24)))
        self.assertIsNone(updates.due(self.runtime, old, self.now - timedelta(hours=1)))
        old["status"] = "offline"
        self.assertEqual(updates.due(self.runtime, old, self.now + timedelta(minutes=4)), "retry_backoff")
        self.assertIsNone(updates.due(self.runtime, old, self.now + timedelta(minutes=5)))
        self.assertIsNone(updates.timestamp("2026-01-01T00:00:00"))

    def test_offline_failures_back_off_exponentially_and_recovery_resets(self):
        for count in range(1, 11):
            previous = updates.load_state(self.home)
            updates.save_result(self.home, {"stale": True, "current_version": "2.4.0"}, previous, self.now)
            state = updates.load_state(self.home)
            self.assertEqual(updates.timestamp(state["next_check_at"]) - self.now,
                             timedelta(minutes=min(360, 5 * 2 ** (count - 1))))
        updates.save_result(self.home, {"current_version": "2.4.0"}, state, self.now)
        state = updates.load_state(self.home)
        self.assertEqual(state["failure_count"], 0)
        self.assertEqual(updates.timestamp(state["next_check_at"]) - self.now, timedelta(hours=24))

    def test_approval_notice_is_deduplicated_and_plain_checks_are_quiet(self):
        approval = {"approval_required": True, "latest_version": "3.0.0", "approval_reason": "major_version", "notice": "Review synthetic release."}
        first = updates.save_result(self.home, dict(approval), {}, self.now)
        self.assertTrue(first["notify"])
        again = updates.save_result(self.home, dict(approval), updates.load_state(self.home), self.now + timedelta(days=1))
        self.assertFalse(again["notify"])
        self.assertNotIn("notice", again)
        plain = updates.save_result(self.home, {"updated": False}, updates.load_state(self.home), self.now)
        self.assertFalse(plain["notify"])

    def test_preferences_are_offline_shared_and_fail_closed(self):
        with mock.patch.object(bootstrap, "release_versions", side_effect=AssertionError("network not allowed")):
            for action, reason in (("disable", "automatic_updates_disabled"), ("pin", "automatic_updates_disabled"), ("enable", "version_pinned")):
                bootstrap.update_preferences(self.home, action)
                self.assertEqual(bootstrap.automatic_update(self.home)["reason"], reason)
            bootstrap.update_preferences(self.home, "unpin")
            self.assertIsNone(bootstrap.update_preferences(self.home, "status")["pinned_version"])
        self.runtime["automatic_updates"] = "yes"
        bootstrap.save_config(self.home, {"schema": bootstrap.CONFIG_SCHEMA, "runtime": self.runtime})
        self.assertEqual(bootstrap.automatic_update(self.home)["reason"], "update_policy_invalid")
        self.assertEqual((self.home / ".megabrain/config.json").stat().st_mode & 0o777, 0o600)

    def test_failed_check_is_cached_and_interrupted_check_has_retry_boundary(self):
        with mock.patch.object(bootstrap, "release_versions", side_effect=bootstrap.BootstrapError("REMOTE_UNREACHABLE", "Synthetic failure")) as check:
            self.assertTrue(bootstrap.automatic_update(self.home)["stale"])
            self.assertEqual(bootstrap.automatic_update(self.home)["reason"], "retry_backoff")
            self.assertEqual(check.call_count, 1)
        bootstrap.update_preferences(self.home, "enable")
        with mock.patch.object(bootstrap, "_update_runtime", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                bootstrap.automatic_update(self.home)
        self.assertEqual(updates.load_state(self.home)["status"], "checking")
        self.assertEqual(bootstrap.automatic_update(self.home)["reason"], "retry_backoff")

    def test_source_tree_and_unconfigured_calls_do_not_update(self):
        with mock.patch.dict(os.environ, {"HOME": str(self.home)}), mock.patch.object(bootstrap, "automatic_update", side_effect=AssertionError("not installed")):
            self.assertIsNone(fixtures.megabrain_runtime.automatic_runtime_update())
        bootstrap.config_path(self.home).unlink()
        self.assertEqual(bootstrap.automatic_update(self.home)["reason"], "setup_required")

    def test_subprocesses_share_one_foreground_budget(self):
        start = time.monotonic()
        with operations.deadline(0.15):
            result = operations.run([sys.executable, "-c", "import time; time.sleep(10)"])
            self.assertEqual(result.returncode, 124)
            with mock.patch.object(subprocess, "Popen", side_effect=AssertionError("budget exhausted")):
                self.assertEqual(operations.run(["git", "--version"]).returncode, 124)
        self.assertLess(time.monotonic() - start, 2)
        self.assertEqual(operations.run([sys.executable, "-c", "pass"]).returncode, 0)

    def test_concurrent_agents_only_one_checks_and_busy_read_does_not_wait(self):
        script = (
            f"import sys,time; sys.path.insert(0, {str(fixtures.SCRIPTS)!r}); import bootstrap\n"
            "from pathlib import Path\n"
            f"home=Path({str(self.home)!r})\n"
            "def check(remote):\n"
            " with (home/'checks').open('a') as stream: stream.write('check\\n')\n"
            " time.sleep(.3)\n"
            " return [((2,4,0), 'v2.4.0')]\n"
            "bootstrap.release_versions=check\n"
            "import json; print(json.dumps(bootstrap.automatic_update(home)))\n"
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: fixtures.run([sys.executable, "-c", script], self.home), range(4)))
        self.assertEqual((self.home / "checks").read_text().splitlines(), ["check"])
        self.assertEqual(sum(json.loads(result.stdout).get("checked", False) for result in results), 1)
        bootstrap.update_preferences(self.home, "enable")
        with operations.lock(self.home, name="runtime"):
            start = time.monotonic()
            result = fixtures.run([sys.executable, "-c", script], self.home)
            self.assertEqual(json.loads(result.stdout)["reason"], "brain_busy")
            self.assertLess(time.monotonic() - start, 2)


class InstalledUpdateTests(unittest.TestCase):
    def setUp(self):
        self.network = fixtures.BrainNetwork()
        self.home = self.network.root / "updater-home"
        self.home.mkdir()
        self.current = bootstrap.runtime_metadata(fixtures.SCRIPTS.parent)["version"]
        major, minor, _ = map(int, self.current.split("."))
        self.next = f"{major}.{minor + 1}.0"

    def tearDown(self):
        self.network.close()

    def install(self, *, versions=None, **kwargs):
        self.work, self.remote, _ = fixtures.MegaBrainAcceptanceTests.create_runtime_distribution(
            self, "updates", versions or [], **kwargs)
        self.connect("codex")
        self.command = self.home / ".local/bin/megabrain"
        self.root = self.home / ".megabrain/clones/codex"

    def connect(self, harness):
        fixtures.run([sys.executable, str(self.work / "install.py"), "setup", "--harness", harness,
                      "--home", str(self.home), "--repository", str(self.network.remote), "--allow-local-remote",
                      "--distribution", str(self.remote), "--no-open"], self.work)

    def call(self, *args, payload=None, harness=None, expected=0):
        return fixtures.run([str(self.command), *args], self.home, stdin=payload, expected=expected,
                            env={"HOME": str(self.home), "MEGABRAIN_HARNESS": harness or "codex"})

    def publish(self):
        manifest = self.work / "skill/megabrain/runtime.json"
        metadata = json.loads(manifest.read_text())
        metadata["version"] = self.next
        manifest.write_text(json.dumps(metadata) + "\n")
        for relative, marker in (("assets/browser.html", "<!-- SYNTHETIC NEXT ASSET -->"), ("SKILL.md", "\nSynthetic next instructions.\n")):
            path = self.work / "skill/megabrain" / relative
            path.write_text(path.read_text() + marker)
        fixtures.run(["git", "add", "skill"], self.work)
        fixtures.run(["git", "commit", "-m", "test: next synthetic runtime"], self.work)
        fixtures.run(["git", "tag", f"v{self.next}"], self.work)
        fixtures.run(["git", "push", "release", f"v{self.next}"], self.work)
        fixtures.run(["git", "checkout", f"v{self.current}"], self.work)

    def force_due(self):
        bootstrap.update_preferences(self.home, "enable")

    def test_every_normal_read_triggers_but_writes_help_and_status_do_not(self):
        self.install()
        self.publish()
        self.call("remember", "--stdin", payload={"kind": "fact", "subject": "synthetic.update", "summary": "Synthetic retained evidence.",
            "confidence": "confirmed", "sensitivity": "general", "importance": "normal", "tags": [], "source": {"type": "user-statement"}})
        for args in (("search", "--help"), ("status",), ("updates", "status", "--json")):
            self.call(*args)
        self.assertFalse(bootstrap.update_state_path(self.home).exists())
        from tests import test_canonical as resources
        created = resources.canonical_local.create_or_revise_resource(
            self.root, resources.CanonicalRepositoryTests.resource_payload(self), trusted_local=True)
        uri = created["resource"]["uri"]
        head = operations.git_text(self.root, "rev-parse", "HEAD")
        tree = operations.git_text(self.root, "rev-parse", "HEAD:brain")
        for args, payload in ((("context", "--stdin"), {"task": "synthetic"}), (("search", "--stdin"), {"query": "synthetic"}),
                              (("resources", "--stdin"), {}), (("resource-read", uri), None), (("review",), None), (("browse", "--no-open"), None)):
            with self.subTest(command=args[0]):
                self.call("updates", "unpin")
                result = json.loads(self.call(*args, payload=payload).stdout)
                self.assertTrue(result["runtime_update"]["updated"])
                self.assertTrue(result["runtime_update"]["skill_reload_required"])
                self.assertEqual(result["runtime_update"]["applies_to"], "next_operation")
                self.assertEqual(bootstrap.load_config(self.home)["runtime"]["version"], self.next)
                self.call("update", "--version", self.current, "--json")
        self.assertEqual(operations.git_text(self.root, "rev-parse", "HEAD"), head)
        self.assertEqual(operations.git_text(self.root, "rev-parse", "HEAD:brain"), tree)
        self.assertEqual(operations.git_text(self.root, "status", "--porcelain"), "")
        self.assertEqual(updates.READ_COMMANDS, {"context", "search", "resources", "resource-read", "browse", "review"})

    def test_open_notifies_once_and_inflight_assets_remain_on_original_release(self):
        self.install()
        self.publish()
        first = self.call("open", "--no-open").stdout
        self.assertIn(f"updated to v{self.next}", first)
        self.assertIn("Reload the MegaBrain skill", first)
        # The request that performed activation finished with its original template.
        snapshots = list((self.root / ".megabrain").rglob("*.html"))
        self.assertEqual(len(snapshots), 1)
        snapshot = snapshots[0]
        self.assertNotIn("SYNTHETIC NEXT ASSET", snapshot.read_text())
        second = self.call("open", "--no-open").stdout
        self.assertNotIn("updated to", second)
        self.assertIn("SYNTHETIC NEXT ASSET", snapshot.read_text())
        # Installed helper entrypoints still resolve harness identity after pinning imports.
        helper = self.home / ".codex/skills/megabrain/scripts/megabrain.py"
        result = fixtures.run([sys.executable, str(helper), "context", "--stdin"], self.home,
                              stdin={"task": "synthetic"}, env={"HOME": str(self.home)})
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_disable_survives_connect_and_all_harnesses_share_one_daily_state(self):
        self.install()
        self.call("updates", "disable")
        self.connect("claude")
        self.connect("hermes")
        self.publish()
        for harness in ("codex", "claude", "hermes"):
            self.assertNotIn("runtime_update", json.loads(self.call("context", "--stdin", payload={"task": "synthetic"}, harness=harness).stdout))
        self.assertEqual(bootstrap.load_config(self.home)["runtime"]["version"], self.current)
        self.call("updates", "enable")
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda harness: json.loads(self.call("context", "--stdin", payload={"task": "synthetic"}, harness=harness).stdout), ("codex", "claude", "hermes")))
        self.assertEqual(sum("runtime_update" in result for result in results), 1)
        self.assertEqual(bootstrap.load_config(self.home)["runtime"]["version"], self.next)

    def test_invalid_and_incompatible_releases_leave_reads_available(self):
        self.install(versions=[self.next], invalid_version=self.next)
        result = json.loads(self.call("search", "--stdin", payload={"query": "synthetic"}).stdout)
        self.assertTrue(result["ok"])
        self.assertNotIn("runtime_update", result)
        self.assertEqual(updates.load_state(self.home)["status"], "failed")
        self.assertEqual(bootstrap.load_config(self.home)["runtime"]["version"], self.current)
        self.assertEqual(bootstrap.automatic_update(self.home)["reason"], "retry_backoff")

    def test_offline_normal_read_and_dirty_clone_are_preserved(self):
        self.install()
        self.publish()
        dirty = self.root / "synthetic-uncommitted.txt"
        head = operations.git_text(self.root, "rev-parse", "HEAD")
        missing = self.remote.with_name("offline-release.git")
        self.remote.rename(missing)
        first = json.loads(self.call("search", "--stdin", payload={"query": "synthetic"}).stdout)
        self.assertTrue(first["ok"])
        self.assertNotIn("runtime_update", first)
        self.assertEqual(updates.load_state(self.home)["status"], "failed")
        missing.rename(self.remote)
        self.force_due()
        dirty.write_text("Synthetic work must be retained.\n")
        # A warmed committed projection remains usable; dirty data is not indexed.
        retained = json.loads(self.call("search", "--stdin", payload={"query": "synthetic"}).stdout)
        self.assertTrue(retained["runtime_update"]["updated"])
        self.assertNotIn("Synthetic work must be retained", json.dumps(retained))
        self.assertEqual(bootstrap.load_config(self.home)["runtime"]["version"], self.next)
        self.assertEqual(dirty.read_text(), "Synthetic work must be retained.\n")
        self.assertEqual(operations.git_text(self.root, "rev-parse", "HEAD"), head)

    def test_activation_cannot_interrupt_a_durable_write(self):
        self.install(versions=[self.next])
        with operations.lock(self.home, name="runtime-use", shared=True):
            checked = self.call("context", "--stdin", payload={"task": "synthetic"})
            self.assertTrue(json.loads(checked.stdout)["ok"])
            self.assertEqual(bootstrap.load_config(self.home)["runtime"]["version"], self.current)
            self.assertEqual(updates.load_state(self.home)["reason"], "brain_busy")
            self.assertFalse(bootstrap.runtime_journal(self.home).exists())
        self.force_due()
        self.assertTrue(bootstrap.automatic_update(self.home)["updated"])

    def test_automatic_protocol_transition_needs_approval(self):
        self.install(versions=[self.next], protocol_versions={self.next: 3})
        first = json.loads(self.call("search", "--stdin", payload={"query": "synthetic"}).stdout)
        self.assertEqual(first["runtime_update"]["approval_reason"], "protocol_version")
        self.assertEqual(bootstrap.load_config(self.home)["runtime"]["version"], self.current)

    def test_automatic_major_approval_never_activates_or_repeats_notice(self):
        next_major = f"{int(self.current.split('.')[0]) + 1}.0.0"
        self.install(versions=[next_major])
        first = json.loads(self.call("context", "--stdin", payload={"task": "synthetic"}).stdout)
        self.assertEqual(first["runtime_update"]["approval_reason"], "major_version")
        self.force_due()
        second = json.loads(self.call("context", "--stdin", payload={"task": "synthetic"}).stdout)
        self.assertNotIn("runtime_update", second)
        self.assertEqual(bootstrap.load_config(self.home)["runtime"]["version"], self.current)

    def test_activation_failure_and_interrupted_switch_restore_previous_runtime(self):
        self.install(versions=[self.next])
        old_config = bootstrap.load_config(self.home)
        old_link = bootstrap.current_runtime(self.home).resolve()
        original_save = bootstrap.save_config
        def fail_new(home, config):
            if config["runtime"]["version"] == self.next:
                raise OSError("synthetic interruption")
            original_save(home, config)
        with mock.patch.object(bootstrap, "save_config", side_effect=fail_new):
            result = bootstrap.automatic_update(self.home)
        self.assertTrue(result["stale"])
        self.assertEqual(bootstrap.current_runtime(self.home).resolve(), old_link)
        self.assertEqual(bootstrap.load_config(self.home), old_config)
        self.assertFalse(bootstrap.runtime_journal(self.home).exists())
        # Simulate abrupt death after link and config replacement but before receipt removal.
        bootstrap.save_private_json(bootstrap.runtime_journal(self.home), {"previous_runtime": old_config["runtime"], "target_version": self.next,
            "next_runtime": {**old_config["runtime"], "version": self.next}})
        bootstrap.activate_runtime(self.home, self.next)
        bootstrap.save_config(self.home, {**old_config, "runtime": {**old_config["runtime"], "version": self.next}})
        self.assertTrue(bootstrap.update_preferences(self.home, "status")["recovery_pending"])
        with self.assertRaises(bootstrap.BootstrapError) as blocked:
            bootstrap.update_runtime(argparse.Namespace(home=self.home, automatic=False, check=True, version=None))
        self.assertEqual(blocked.exception.code, "RUNTIME_RECOVERY_REQUIRED")
        self.assertEqual(bootstrap.load_config(self.home)["runtime"]["version"], self.next)
        bootstrap.automatic_update(self.home)
        self.assertEqual(bootstrap.current_runtime(self.home).resolve(), old_link)
        self.assertEqual(bootstrap.load_config(self.home), old_config)
        self.assertFalse(bootstrap.runtime_journal(self.home).exists())

    def test_unrecorded_runtime_changes_require_review_without_repair(self):
        self.install()
        config = bootstrap.load_config(self.home)
        journal = {"previous_runtime": config["runtime"], "target_version": self.next,
                   "next_runtime": {**config["runtime"], "version": self.next}}
        bootstrap.save_private_json(bootstrap.runtime_journal(self.home), journal)
        unrelated = self.network.root / "unrelated-runtime"
        unrelated.mkdir()
        current = bootstrap.current_runtime(self.home)
        current.unlink()
        current.symlink_to(unrelated)
        result = bootstrap.automatic_update(self.home)
        self.assertEqual(result["reason"], "runtime_recovery_required")
        self.assertEqual(current.resolve(), unrelated.resolve())
        self.assertEqual(bootstrap.load_config(self.home), config)
        self.assertTrue(bootstrap.runtime_journal(self.home).exists())

    def test_legacy_rollback_cannot_silently_drop_pin_enforcement(self):
        self.install()
        legacy = f"{int(self.current.split('.')[0])}.0.0"
        source = self.network.root / "synthetic-legacy"
        shutil.copytree(fixtures.SCRIPTS.parent, source)
        metadata = json.loads((source / "runtime.json").read_text())
        metadata["version"] = legacy
        metadata.pop("update_policy_version")
        (source / "runtime.json").write_text(json.dumps(metadata))
        bootstrap.copy_runtime_release(source, bootstrap.runtime_release(self.home, legacy))
        with mock.patch.object(bootstrap, "release_versions", return_value=[(bootstrap.semantic_version(legacy), f"v{legacy}")]):
            with self.assertRaises(bootstrap.BootstrapError) as failure:
                bootstrap.update_runtime(argparse.Namespace(home=self.home, automatic=False, check=False, version=legacy, approve_major=False))
        self.assertEqual(failure.exception.code, "LEGACY_ROLLBACK_UNSAFE")
        self.assertEqual(bootstrap.load_config(self.home)["runtime"]["version"], self.current)

    def test_pinned_rollback_stays_pinned_across_check_and_time_and_prevents_setup_bypass(self):
        self.install(versions=[self.next])
        self.call("update", "--json")
        rolled = json.loads(self.call("update", "--version", self.current, "--json").stdout)
        self.assertEqual(rolled["pinned_version"], self.current)
        bootstrap.update_state_path(self.home).unlink()
        checked = self.call("update", "--check", "--json")
        self.assertTrue(json.loads(checked.stdout)["update_available"])
        self.assertFalse(bootstrap.update_state_path(self.home).exists())
        self.assertEqual(bootstrap.automatic_update(self.home)["reason"], "version_pinned")
        self.call("update", "--json")
        self.assertEqual(bootstrap.load_config(self.home)["runtime"]["version"], self.current)
        fixtures.run(["git", "checkout", f"v{self.next}"], self.work)
        blocked = fixtures.run([sys.executable, str(self.work / "install.py"), "setup", "--harness", "codex", "--home", str(self.home)], self.work, expected=2)
        self.assertEqual(json.loads(blocked.stderr)["error"]["code"], "RUNTIME_PINNED")
        self.call("updates", "unpin")
        self.assertTrue(bootstrap.automatic_update(self.home)["updated"])


if __name__ == "__main__":
    unittest.main()
