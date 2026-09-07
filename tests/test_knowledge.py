"""Owner control and review behavior using synthetic records only."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from tests.test_megabrain import BrainNetwork, megabrain_runtime as mb
from tests.test_canonical import canonical_local
import canonical
import operations


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.network = BrainNetwork()
        self.root = self.network.clone("knowledge", "codex")

    def tearDown(self):
        self.network.close()

    def call(self, command, payload=None, *args, expected=0):
        return self.network.command("knowledge", command, payload, *args, expected=expected)

    def resource(self, sensitivity="general"):
        return canonical_local.create_or_revise_resource(self.root, {
            "resource_type": "runbook", "title": "Synthetic gateway recovery", "owner": "synthetic-owner",
            "authority_domain": "synthetic-project", "sensitivity": sensitivity,
            "source_at": "2020-01-01T00:00:00Z", "verified_at": "2020-01-01T00:00:00Z", "freshness_at": None,
            "source": {"type": "user-statement", "locator": "synthetic://gateway", "fingerprint": canonical.content_fingerprint("Synthetic steps.")},
            "body": "# Recovery\n\nSynthetic steps.\n\n<script>window.syntheticInjection=true</script>",
        }, trusted_local=True)

    def test_pause_explicit_capture_skip_and_resume(self):
        self.call("capture", None, "pause")
        self.assertEqual(self.network.remember("knowledge")["reason"], "capture_paused")
        self.assertTrue(self.network.remember("knowledge", capture="explicit")["created"])
        self.assertEqual(self.network.remember("knowledge", capture="skip")["reason"], "capture_skipped")
        self.call("capture", None, "resume")
        self.assertTrue(self.network.remember("knowledge", subject="synthetic.second")["created"])
        self.assertEqual(len(mb.load_memories(self.root)), 2)

    def test_review_reports_uncertainty_due_dates_duplicates_and_resource_age(self):
        first = self.call("remember", {"subject": "synthetic.alpha", "summary": "Synthetic shared fact.",
                          "sensitivity": "general", "source": {"type": "agent-observation"}, "review_after": "2020-01-01T00:00:00Z"}, "--stdin")
        self.network.remember("knowledge", subject="synthetic.beta", summary="Synthetic shared fact.")
        self.resource()
        result = self.call("review")
        item = next(item for item in result["items"] if item["citation"].get("memory_id") == first["memory_id"])
        self.assertEqual(set(item["reasons"]), {"needs_confirmation", "review_due", "possible_duplicate"})
        self.assertTrue(any("verification_old" in item["reasons"] for item in result["items"]))
        bounded = self.call("review", {"limit": 1}, "--stdin")
        self.assertEqual(len(bounded["items"]), 1)
        self.assertTrue(bounded["truncated"])

    def test_handoffs_are_immutable_owner_review_proposals(self):
        created = self.network.remember("knowledge", sensitivity="private")
        before = operations.git_text(self.root, "rev-parse", "HEAD")
        result = self.call("handoff", {"action": "forget", "id": created["memory_id"]}, "--stdin")
        self.assertTrue(result["requires_owner_approval"])
        self.assertIn("Git history remains", result["prompt"])
        self.assertEqual(operations.git_text(self.root, "rev-parse", "HEAD"), before)
        with self.assertRaises(operations.OperationError):
            mb.command_handoff(self.root, {"action": "forget", "id": created["memory_id"]})

    def test_home_includes_resources_review_and_safe_inert_markup(self):
        self.resource()
        self.network.remember("knowledge", confidence="unconfirmed")
        result = self.call("browse", None, "--no-open")
        html = Path(result["path"]).read_text()
        self.assertIn('data-view="resources"', html)
        self.assertIn('data-view="review"', html)
        self.assertNotIn("<script>window.syntheticInjection", html)
        self.assertIn("window.syntheticInjection", html)
        self.assertIn("Nothing has been changed.", html)
        self.assertIn("Clipboard unavailable", html)

    def test_hidden_correction_never_resurrects_a_general_memory(self):
        original = self.network.remember("knowledge", sensitivity="general")
        self.call("correct", {"summary": "Synthetic protected correction.", "sensitivity": "private"}, original["memory_id"], "--stdin")
        data = mb.browser_payload(self.root, {"synced": True})
        self.assertEqual(data["stats"]["current"], 0)
        self.assertEqual(data["memories"][0]["status"], "historical")
