"""Content-tree reuse, incremental parsing, recovery and installed-harness checks."""
from __future__ import annotations

import json
from unittest import mock
import unittest

from tests.test_megabrain import BrainNetwork, megabrain_runtime as mb, run
from tests.test_canonical import canonical_local
import canonical
import operations


class ScaleTests(unittest.TestCase):
    def setUp(self):
        self.network = BrainNetwork()
        self.root = self.network.clone("scale", "codex")

    def tearDown(self):
        self.network.close()

    def memories(self):
        return mb.indexed_memories(self.root, {"synthetic"})

    def test_content_tree_reuse_and_only_new_blob_parsing(self):
        self.network.remember("scale")
        self.assertEqual(self.memories()[2], "cold")
        canonical.search_resources(self.root, set())
        self.network.remember("scale", subject="synthetic.second")
        with mock.patch.object(mb, "parse_record_text", wraps=mb.parse_record_text) as parse:
            self.assertEqual(self.memories()[2], "cold")
            self.assertEqual(parse.call_count, 1)
        self.assertEqual(canonical.search_resources(self.root, set())[2], "warm")
        (self.root / "synthetic-note.md").write_text("Synthetic non-knowledge note.\n")
        run(["git", "add", "synthetic-note.md"], self.root)
        run(["git", "commit", "-m", "test: unrelated tree"], self.root)
        self.assertEqual(self.memories()[2], "warm")
        self.assertEqual(canonical.search_resources(self.root, set())[2], "warm")

    def test_interrupted_rebuild_preserves_old_index_and_corruption_rebuilds(self):
        self.network.remember("scale")
        self.memories()
        path = mb.retrieval_index_path(self.root)
        before = path.read_bytes()
        self.network.remember("scale", subject="synthetic.second")
        with mock.patch.object(mb.os, "replace", side_effect=OSError("synthetic interruption")):
            with self.assertRaises(OSError):
                self.memories()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(self.memories()[0]), 2)
        path.write_bytes(b"synthetic corrupt disposable index")
        self.assertEqual(len(self.memories()[0]), 2)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_policy_snapshot_is_shared_but_never_survives_an_operation(self):
        policy = canonical.current_policies(self.root)[0]
        context = {"agent_id": policy["agent_id"], "source_kind": policy["source_kinds"][0],
                   "platform": policy["platforms"][0], "chat_type": policy["chat_types"][0], "owner_verified": True}
        meta = {"sensitivity": "private", "subject": "synthetic.policy", "tags": []}
        with operations.lock(self.root), mock.patch.object(canonical, "load_policies", wraps=canonical.load_policies) as load:
            for _ in range(3):
                self.assertTrue(canonical.authorize_memory_read(self.root, meta, context))
            self.assertEqual(load.call_count, 1)
        canonical_local.set_policy(self.root, {"policy_id": policy["policy_id"]}, revoke=True, trusted_local=True)
        with operations.lock(self.root):
            self.assertFalse(canonical.authorize_memory_read(self.root, meta, context))

    def test_dirty_policy_cannot_grant_access(self):
        policy = canonical.current_policies(self.root)[0]
        context = {"agent_id": policy["agent_id"], "source_kind": policy["source_kinds"][0],
                   "platform": "synthetic-untrusted", "chat_type": policy["chat_types"][0], "owner_verified": True}
        path = canonical.policy_path(self.root, policy)
        policy["platforms"].append("synthetic-untrusted")
        path.write_text(json.dumps(policy))
        with operations.lock(self.root):
            self.assertFalse(canonical.authorize_memory_read(self.root, {"sensitivity": "private"}, context))

    def test_bounded_process_timeout_terminates_without_output(self):
        import sys
        result = operations.run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.1)
        self.assertEqual(result.returncode, 124)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_installed_codex_claude_and_hermes_owner_journey(self):
        for harness in ("codex", "claude", "hermes"):
            with self.subTest(harness=harness):
                name = "scale" if harness == "codex" else harness
                if name != "scale":
                    self.network.clone(name, harness)
                home = self.network.homes[name]
                command = home / ".local/bin/megabrain"
                def call(*args, payload=None, expected=0):
                    response = run([str(command), *args], home, stdin=payload, expected=expected,
                                   env={"HOME": str(home), "MEGABRAIN_HARNESS": harness})
                    return json.loads(response.stdout or response.stderr)
                self.assertTrue(call("status")["ready"])
                if harness == "hermes":
                    self.assertEqual(call("capture", "pause", expected=2)["error"]["code"], "OWNER_CONTEXT_REQUIRED")
                else:
                    call("capture", "pause")
                payload = {"subject": f"synthetic.{harness}.journey", "summary": "Synthetic onboarding checkpoint.",
                           "sensitivity": "general", "source": {"type": "user-statement"}}
                if harness != "hermes":
                    self.assertFalse(call("remember", "--stdin", payload=payload)["created"])
                created = call("remember", "--stdin", payload={**payload, "capture": "explicit"})
                self.assertTrue(created["pushed"])
                evidence = call("search", "--stdin", payload={"query": "synthetic onboarding checkpoint"})
                self.assertIn(created["memory_id"], [item["citation"].get("memory_id") for item in evidence["evidence"]])
                handoff = call("handoff", "--stdin", payload={"action": "forget", "id": created["memory_id"]})
                self.assertTrue(handoff["requires_owner_approval"])
                self.assertTrue(call("forget", created["memory_id"], "--stdin", payload={})["created"])
                if harness != "hermes":
                    call("capture", "resume")
                self.assertTrue(call("validate")["ok"])
