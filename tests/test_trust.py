"""Regression evidence for the trust-repair milestone. Synthetic data only."""
from __future__ import annotations

import concurrent.futures
import json
import os
from pathlib import Path
import stat
import sys
import time
import unittest

from tests.test_megabrain import BrainNetwork, SCRIPTS, megabrain_runtime as mb, run
import bootstrap
import operations


class TrustRepairTests(unittest.TestCase):
    def setUp(self):
        self.network = BrainNetwork()
        self.root = self.network.clone("trust", "codex")
        self.home = self.network.homes["trust"]

    def tearDown(self):
        self.network.close()

    def commit(self, message="test: synthetic change"):
        run(["git", "add", "."], self.root)
        run(["git", "commit", "-m", message], self.root)

    def test_secret_removed_from_head_is_still_blocked_in_outgoing_history(self):
        before = operations.git_text(self.network.remote, "rev-parse", "main")
        path = self.root / "temporary-note.txt"
        path.write_text("sk-" + "Z" * 30)
        self.commit()
        path.unlink()
        self.commit()
        self.assertTrue(mb.command_validate(self.root)["ok"])
        result = mb.sync_repo(self.root)
        self.assertEqual(result["guard"], "outgoing_secret_rejected")
        self.assertNotIn("ZZZZ", json.dumps(result))
        self.assertEqual(operations.git_text(self.network.remote, "rev-parse", "main"), before)

    def test_modification_and_deletion_of_published_memory_are_blocked(self):
        self.network.remember("trust", summary="Synthetic original memory.")
        path = mb.memory_files(self.root)[0]
        path.write_text(path.read_text().replace("Synthetic original", "Synthetic modified"))
        self.commit()
        self.assertTrue(mb.command_validate(self.root)["ok"])
        self.assertEqual(mb.sync_repo(self.root)["guard"], "immutable_history_rejected")
        path.unlink()
        self.commit()
        self.assertEqual(mb.sync_repo(self.root)["guard"], "immutable_history_rejected")

    def test_browser_filters_protected_content_and_ignores_dirty_records(self):
        self.network.remember("trust", subject="synthetic.private", summary="Synthetic private marker.", sensitivity="private")
        self.network.remember("trust", subject="synthetic.sensitive", summary="Synthetic sensitive marker.", sensitivity="sensitive")
        plain = mb.command_browse(self.root, True)
        text = Path(plain["path"]).read_text()
        self.assertNotIn("Synthetic private marker", text)
        self.assertNotIn("Synthetic sensitive marker", text)
        self.assertEqual(stat.S_IMODE(Path(plain["path"]).stat().st_mode), 0o600)
        installed = self.network.command("trust", "browse", None, "--no-open")
        text = Path(installed["path"]).read_text()
        self.assertIn("Synthetic private marker", text)
        self.assertNotIn("Synthetic sensitive marker", text)
        mb.create_memory_file(self.root, mb.load_identity(self.root), {
            "subject": "synthetic.dirty", "summary": "Synthetic dirty marker.", "sensitivity": "general",
        })
        dirty = mb.command_browse(self.root, True)
        self.assertEqual(dirty["sync"]["reason"], "dirty_worktree")
        self.assertNotIn("Synthetic dirty marker", Path(dirty["path"]).read_text())

    def test_runtime_inventory_and_startup_fail_closed(self):
        target = self.network.root / "test-release"
        bootstrap.copy_runtime_release(SCRIPTS.parent, target)
        path = target / "skill/megabrain/scripts/canonical.py"
        path.unlink()
        with self.assertRaises(bootstrap.BootstrapError):
            bootstrap.validate_runtime_release(target)

    def test_same_clone_concurrent_writes_do_not_mix_or_lose_commits(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda number: self.network.remember(
                "trust", subject=f"synthetic.concurrent.{number}", summary=f"Synthetic value {number}."
            ), range(3)))
        self.assertTrue(all(result["created"] and result["pushed"] for result in results))
        self.assertEqual(len(mb.load_memories(self.root)), 3)
        self.assertEqual(operations.git_text(self.root, "status", "--porcelain"), "")

    def test_bounded_subprocess_discards_partial_output(self):
        started = time.monotonic()
        result = operations.run([sys.executable, "-c", "import time; print('synthetic partial'); time.sleep(10)"], timeout=0.1)
        self.assertEqual(result.returncode, 124)
        self.assertEqual(result.stdout, "")
        self.assertLess(time.monotonic() - started, 3)

    def test_backup_restore_rehearsal_preserves_history_without_replacing_clone(self):
        import recovery
        self.network.remember("trust", summary="Synthetic recovery anchor.")
        bundle = self.network.root / "recovery.bundle"
        receipt = recovery.backup(self.root, bundle)
        destination = self.network.root / "recovered"
        restored = recovery.restore(bundle, destination, receipt["sha256"])
        self.assertEqual(restored["commit"], receipt["commit"])
        self.assertFalse(restored["connected"])
        self.assertEqual(len(mb.load_memories(destination)), 1)
        self.assertEqual(stat.S_IMODE(bundle.stat().st_mode), 0o600)
        with self.assertRaises(operations.OperationError):
            recovery.restore(bundle, self.root, receipt["sha256"])
        with self.assertRaises(operations.OperationError):
            recovery.restore(bundle, self.network.root / "invalid", "0" * 64)

    def test_immutable_creation_is_exclusive(self):
        path = self.network.root / "synthetic" / "entry.md"
        operations.atomic_write(path, "first", exclusive=True)
        with self.assertRaises(FileExistsError):
            operations.atomic_write(path, "second", exclusive=True)
        self.assertEqual(path.read_text(), "first")

    def test_symlink_output_is_rejected_without_touching_target(self):
        target = self.network.root / "untouched.txt"
        target.write_text("synthetic original")
        link = self.network.root / "link.txt"
        link.symlink_to(target)
        with self.assertRaises(operations.OperationError):
            operations.atomic_write(link, "replacement")
        self.assertEqual(target.read_text(), "synthetic original")
