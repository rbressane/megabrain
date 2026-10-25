"""Owner control, review, inbox ingest, and knowledge health using synthetic records only."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from tests.test_megabrain import BrainNetwork, megabrain_runtime as mb
from tests.test_canonical import canonical_local
import canonical
import knowledge
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

    def test_health_report_is_read_only_and_flags_dead_links_orphans_conflicts_and_gaps(self):
        missing = "01234567-89ab-4cde-8f01-23456789abcd"
        report = knowledge.health_report(
            [
                {
                    "id": "11111111-1111-4111-8111-111111111111",
                    "kind": "fact",
                    "subject": "synthetic.cited",
                    "status": "current",
                    "summary": f"See megabrain://resource/{missing} and the live gateway.",
                    "supersedes": ["22222222-2222-4222-8222-222222222222"],
                    "importance": "normal",
                    "confidence": "confirmed",
                    "authority_domain": "alpha",
                },
                {
                    "id": "33333333-3333-4333-8333-333333333333",
                    "kind": "commitment",
                    "subject": "synthetic.conflict",
                    "status": "current",
                    "summary": "The synthetic channel is stable.",
                    "supersedes": [],
                    "importance": "normal",
                    "confidence": "unconfirmed",
                    "review_after": "2020-01-01T00:00:00Z",
                    "conflict": True,
                },
                {
                    "id": "44444444-4444-4444-8444-444444444444",
                    "kind": "commitment",
                    "subject": "synthetic.conflict",
                    "status": "current",
                    "summary": "The synthetic channel is preview.",
                    "supersedes": [],
                    "importance": "normal",
                    "confidence": "unconfirmed",
                    "conflict": True,
                },
            ],
            [
                {
                    "resource_id": "55555555-5555-4555-8555-555555555555",
                    "revision_id": "66666666-6666-4666-8666-666666666666",
                    "uri": "megabrain://resource/55555555-5555-4555-8555-555555555555",
                    "title": "Synthetic uncited runbook",
                    "status": "current",
                    "body": "No citations here.",
                    "authority_domain": "beta",
                    "verified_at": "2020-01-01T00:00:00Z",
                    "resource_type": "runbook",
                }
            ],
            now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(report["summary"]["dead_links"], 2)
        self.assertEqual({item["reason"] for item in report["dead_links"]}, {"resource_not_found", "unknown_supersedes"})
        self.assertEqual(report["orphans"][0]["reason"], "uncited_current_resource")
        self.assertEqual(report["conflicts"][0]["reason"], "conflicting_claims")
        self.assertIn("review_due", {item["reason"] for item in report["stale"]})
        self.assertEqual({item["reason"] for item in report["gaps"]}, {"review_date_missing", "resource_domain_without_memories"})

    def test_health_command_is_read_only_and_strict_exits_on_findings(self):
        created = self.resource()
        uri = created["resource"]["uri"]
        self.network.remember(
            "knowledge",
            subject="synthetic.dead_link",
            summary=f"Broken pointer megabrain://resource/01234567-89ab-4cde-8f01-23456789abcd.",
            sensitivity="general",
        )
        self.network.remember(
            "knowledge",
            subject="synthetic.gateway",
            summary=f"Use {uri} for the synthetic gateway.",
            authority_domain="synthetic-project",
            sensitivity="general",
        )
        before = operations.git_text(self.root, "rev-parse", "HEAD")
        result = self.call("health")
        self.assertTrue(result["ok"])
        self.assertTrue(result["read_only"])
        self.assertTrue(any(item["reason"] == "resource_not_found" for item in result["dead_links"]))
        self.assertFalse(any(item.get("citation", {}).get("uri") == uri for item in result["orphans"]))
        self.assertEqual(operations.git_text(self.root, "rev-parse", "HEAD"), before)
        self.assertEqual(operations.git_text(self.root, "status", "--porcelain"), "")
        strict = self.call("health", None, "--strict", expected=1)
        self.assertFalse(strict["ok"])
        self.assertGreater(strict["summary"]["findings"], 0)

    def test_inbox_ingests_json_candidates_inventories_raw_files_and_never_rewrites(self):
        existing = self.network.remember("knowledge", subject="synthetic.kept", summary="Keep this existing synthetic fact.")
        inbox = self.root / ".megabrain" / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / "candidate.json").write_text(
            json.dumps({
                "kind": "fact",
                "subject": "synthetic.inbox_decision",
                "summary": "Use the inbox candidate as a sourced synthetic fact.",
                "tags": ["inbox", "synthetic"],
            }),
            encoding="utf-8",
        )
        (inbox / "notes.md").write_text("# Raw synthetic notes\n\nNeeds an agent summary.\n", encoding="utf-8")
        secret = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
        (inbox / "secret.json").write_text(
            json.dumps({"subject": "synthetic.secret", "summary": f"api_key={secret}"}),
            encoding="utf-8",
        )
        before_existing = next((self.root / "brain" / "memories").rglob(f"*-{existing['memory_id']}.md")).read_text(encoding="utf-8")
        first = self.call("ingest", None, "--inbox")
        self.assertEqual(first["status"], "imported")
        self.assertEqual(first["counts"]["created"], 1)
        self.assertEqual(first["counts"]["needs_summary"], 1)
        self.assertEqual(first["counts"]["rejected"], 1)
        self.assertTrue((inbox / "candidate.json").exists())
        self.assertTrue((inbox / "notes.md").exists())
        self.assertNotIn(secret, json.dumps(first))
        kept = next((self.root / "brain" / "memories").rglob(f"*-{existing['memory_id']}.md")).read_text(encoding="utf-8")
        self.assertEqual(kept, before_existing)
        second = self.call("ingest", None, "--inbox")
        self.assertEqual(second["counts"]["unchanged"], 1)
        self.assertEqual(second["counts"]["created"], 0)
        self.assertEqual(second["counts"]["needs_summary"], 1)
