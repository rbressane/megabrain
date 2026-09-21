"""Installed-command contracts and retrieval edge cases, with synthetic brains."""
from __future__ import annotations

import json
import unittest

from tests.test_megabrain import BrainNetwork, SCRIPTS, megabrain_runtime as mb, run
import cli


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.network = BrainNetwork()
        self.root = self.network.clone("interface", "codex")
        self.home = self.network.homes["interface"]
        self.command = self.home / ".local/bin/megabrain"

    def tearDown(self):
        self.network.close()

    def call(self, *args, payload=None, expected=0):
        result = run([str(self.command), *args], self.home, stdin=payload, expected=expected,
                     env={"HOME": str(self.home), "MEGABRAIN_HARNESS": "codex"})
        return json.loads(result.stdout or result.stderr)

    def test_installed_memory_lifecycle_and_scoped_search(self):
        created = self.call("remember", "--stdin", payload={
            "subject": "synthetic.alpha.recovery", "summary": "Synthetic recovery uses a staged restart.",
            "authority_domain": "alpha", "sensitivity": "private", "source": {"type": "user-statement"},
        })
        self.assertTrue(created["pushed"])
        result = self.call("search", "--stdin", payload={"query": "recovery", "authority_domain": "alpha"})
        self.assertEqual(result["evidence"][0]["citation"]["memory_id"], created["memory_id"])
        self.assertEqual(self.call("search", "--stdin", payload={"query": "recovery", "authority_domain": "beta"})["evidence"], [])
        corrected = self.call("correct", created["memory_id"], "--stdin", payload={"summary": "Synthetic recovery uses a verified restart."})
        self.assertTrue(corrected["created"])
        self.assertEqual(self.call("search", "--stdin", payload={"query": "recovery", "authority_domain": "alpha"})["evidence"][0]["authority_domain"], "alpha")
        self.assertTrue(self.call("forget", corrected["memory_id"], "--stdin", payload={})["created"])
        self.assertEqual(self.call("search", "--stdin", payload={"query": "recovery"})["evidence"], [])
        status = self.call("status")
        self.assertTrue(status["ready"])
        self.assertTrue(all(item["ready"] for item in status["capabilities"].values()))
        self.assertTrue(self.call("sync")["synced"])
        self.assertTrue(self.call("validate")["ok"])
        self.assertEqual(self.call("resources", "--stdin", payload={})["resources"], [])

    def test_private_recall_preserves_approximate_and_exact_dates_across_languages(self):
        arrival = self.call("remember", "--stdin", payload={
            "subject": "synthetic.relocation_arrival",
            "summary": "Cheguei a Lisboa aproximadamente em março de 2024.",
            "sensitivity": "private",
            "source": {"type": "user-statement"},
        })
        administrative = self.call("remember", "--stdin", payload={
            "subject": "synthetic.administrative_residence_date",
            "summary": "The exact administrative residence date is 2024-04-17.",
            "sensitivity": "private",
            "source": {"type": "user-statement"},
        })

        portuguese = self.call("search", "--stdin", payload={"query": "quando cheguei a Lisboa"})
        english = self.call("search", "--stdin", payload={"query": "exact administrative residence date"})
        portuguese_ids = {item["citation"].get("memory_id") for item in portuguese["evidence"]}
        english_ids = {item["citation"].get("memory_id") for item in english["evidence"]}
        self.assertIn(arrival["memory_id"], portuguese_ids)
        self.assertIn(administrative["memory_id"], english_ids)
        self.assertNotEqual(arrival["memory_id"], administrative["memory_id"])
        self.assertTrue(all(item["source"]["type"] == "user-statement" for item in english["evidence"]))

    def test_protocol_one_status_and_read_migration_error_are_truthful(self):
        manifest_path = self.root / "megabrain.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({"protocol_version": 1, "minimum_runtime": "1.0.0"})
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        run(["git", "add", "megabrain.json"], self.root)
        run(["git", "commit", "-m", "test: use synthetic protocol one"], self.root)
        run(["git", "push", "origin", "HEAD:main"], self.root)

        status = self.call("status")
        self.assertFalse(status["ready"])
        self.assertTrue(status["capabilities"]["storage"]["ready"])
        self.assertFalse(status["capabilities"]["canonical_search"]["ready"])
        self.assertEqual(
            status["capabilities"]["private_recall"]["reason"],
            "canonical_migration_required",
        )
        failed = self.call("search", "--stdin", payload={"query": "synthetic"}, expected=2)
        self.assertEqual(failed["error"]["code"], "CANONICAL_MIGRATION_REQUIRED")
        self.assertIn("canonical search and resource reads", failed["error"]["message"])
        self.assertNotIn("writes", failed["error"]["message"])

    def test_help_for_every_installed_command_requires_no_brain(self):
        for name in cli.HELPER_COMMANDS:
            result = run(["python3", str(SCRIPTS / "cli.py"), name, "--help"], self.network.root,
                         env={"HOME": str(self.network.root)})
            self.assertIn("usage:", result.stdout)

    def test_stopword_only_query_and_legacy_unscoped_memory(self):
        self.network.remember("interface", importance="always", summary="Keep synthetic evidence explicit.")
        result = self.call("search", "--stdin", payload={"query": "what is it"})
        self.assertEqual(result["query_status"], "no_searchable_terms")
        scoped = self.call("search", "--stdin", payload={"query": "synthetic", "authority_domain": "alpha"})
        self.assertEqual(scoped["evidence"], [])

    def test_conflict_budget_reports_incompleteness(self):
        for number in range(8):
            self.network.remember("interface", subject="synthetic.conflict", summary=f"Synthetic conflict value {number}.")
        result = self.call("search", "--stdin", payload={"query": "synthetic conflict", "limit": 1})
        self.assertEqual(len(result["evidence"]), 6)
        self.assertTrue(result["conflicts_incomplete"])
        self.assertTrue(result["truncated"])

    def test_status_and_errors_do_not_echo_private_paths_or_input(self):
        bad = self.call("search", "--stdin", payload={"query": 42}, expected=2)
        self.assertEqual(bad["error"]["code"], "SEARCH_QUERY_INVALID")
        self.assertNotIn(str(self.home), json.dumps(bad))
        status = self.call("status")
        self.assertNotIn(str(self.home), json.dumps(status))
