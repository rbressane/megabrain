"""Weekly owner digest, using synthetic records only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time
import unittest

from tests.test_automatic_recall import context_of, hook
from tests.test_megabrain import BrainNetwork, megabrain_runtime as mb
import knowledge
import operations

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)


def memory(identifier: str, summary: str, *, subject: str | None = None, kind: str = "fact", days_ago: float = 30,
           confidence: str = "confirmed", status: str = "current", **extra: object) -> dict:
    created = (NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")
    return {"id": identifier, "kind": kind, "subject": subject or f"synthetic.{identifier}", "summary": summary,
            "created_at": created, "created_by": "agent-synthetic", "confidence": confidence, "status": status,
            "conflict": False, "supersedes": [], "review_after": None, **extra}


class DigestLogicTests(unittest.TestCase):
    def test_suggests_merges_confirmations_reviews_and_conflicts(self) -> None:
        records = [
            memory("m1", "The synthetic owner prefers green tea in the morning."),
            memory("m2", "Synthetic owner prefers green tea in the morning.", subject="synthetic.drinks"),
            memory("m3", "The synthetic studio opens at nine.", days_ago=2, confidence="inferred"),
            memory("m4", "The synthetic launch is planned for spring.", review_after="2026-11-01T00:00:00Z"),
            memory("m5", "Synthetic timezone is Lisbon.", subject="synthetic.tz", conflict=True),
            memory("m6", "Synthetic timezone is Tokyo.", subject="synthetic.tz", conflict=True),
            memory("m7", "An unrelated synthetic fact about bicycles."),
        ]
        digest = knowledge.weekly_digest(records, now=NOW)
        kinds = {item["type"]: item for item in digest["suggestions"]}
        self.assertEqual(set(kinds), {"merge", "confirm", "review_due", "settle_conflict"})
        self.assertEqual(sorted(kinds["merge"]["memory_ids"]), ["m1", "m2"])
        self.assertEqual(kinds["confirm"]["memory_ids"], ["m3"])
        self.assertEqual(kinds["review_due"]["memory_ids"], ["m4"])
        self.assertEqual(sorted(kinds["settle_conflict"]["memory_ids"]), ["m5", "m6"])
        self.assertEqual(digest["week"], "2026-W46")
        for item in digest["suggestions"]:
            self.assertTrue(item["requires_owner_approval"])
            self.assertIn("only", item["prompt"].lower())
            for record in records:  # Prompts carry IDs, never memory text.
                self.assertNotIn(record["summary"], item["prompt"])

    def test_one_memory_gets_one_suggestion(self) -> None:
        records = [memory("x", "The synthetic studio opens at nine.", days_ago=1, confidence="inferred",
                          review_after="2026-11-01T00:00:00Z")]
        suggestions = knowledge.weekly_digest(records, now=NOW)["suggestions"]
        self.assertEqual([item["type"] for item in suggestions], ["confirm"])
        self.assertIn("Review was due", suggestions[0]["reason"])

    def test_old_uncertain_memories_and_distinct_facts_are_left_alone(self) -> None:
        records = [
            memory("a", "Synthetic owner likes long walks by the river.", confidence="inferred", days_ago=40),
            memory("b", "Synthetic owner dislikes crowded trains at rush hour."),
        ]
        self.assertEqual(knowledge.weekly_digest(records, now=NOW)["suggestions"], [])

    def test_reports_this_weeks_changes_with_earlier_wording(self) -> None:
        records = [
            memory("old", "Synthetic standup is at ten.", subject="synthetic.standup", status="historical", days_ago=20),
            memory("new", "Synthetic standup is at eleven.", subject="synthetic.standup", days_ago=1, supersedes=["old"]),
            memory("gone", "", kind="tombstone", subject="synthetic.forgotten", days_ago=3, status="tombstone"),
            memory("fresh", "A synthetic fact learned this week.", days_ago=1),
            memory("ancient", "A synthetic fact from long ago.", days_ago=60),
        ]
        digest = knowledge.weekly_digest(records, now=NOW)
        self.assertEqual(digest["counts"], {"suggestions": 0, "learned": 1, "changed": 1, "forgotten": 1})
        self.assertEqual(digest["changed"][0]["before"], ["Synthetic standup is at ten."])

    def test_duplicate_detection_stays_fast_on_a_large_brain(self) -> None:
        records = [memory(f"m{index}", f"Synthetic note {index} about topic{index % 97} and item{index}.") for index in range(5000)]
        started = time.perf_counter()
        knowledge.weekly_digest(records, now=NOW)
        self.assertLess(time.perf_counter() - started, 2.0)


class DigestCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.network = BrainNetwork()
        self.clone = self.network.clone("agent", "codex")

    def tearDown(self) -> None:
        self.network.close()

    def test_digest_command_is_read_only_and_respects_privacy(self) -> None:
        self.network.remember("agent", subject="synthetic.tea", summary="The synthetic owner prefers green tea daily.")
        self.network.remember("agent", subject="synthetic.drink", summary="Synthetic owner prefers green tea daily.")
        hidden = self.network.remember("agent", subject="synthetic.hidden", summary="A private synthetic guess.",
                                       sensitivity="private", confidence="inferred")
        before = operations.git_text(self.clone, "rev-parse", "HEAD")
        result = self.network.command("agent", "digest")
        self.assertTrue(result["ok"])
        self.assertTrue(result["advisory"])
        self.assertIn("merge", {item["type"] for item in result["suggestions"]})
        self.assertNotIn(hidden["memory_id"], json.dumps(result))
        self.assertIn("explicitly approves", result["how_to_use"])
        self.assertEqual(operations.git_text(self.clone, "rev-parse", "HEAD"), before)

    def test_session_start_offers_the_digest_once_a_week(self) -> None:
        self.network.remember("agent", subject="synthetic.studio", summary="The synthetic studio opens at nine.", confidence="inferred")
        output, _ = hook(self.network, "agent", "session-start", {"source": "startup"})
        self.assertIn("weekly digest: 1 suggestion", output["systemMessage"])
        self.assertIn("Never apply a suggestion on your own", context_of(output))
        again, _ = hook(self.network, "agent", "session-start", {"source": "startup"})
        self.assertNotIn("weekly digest", again["systemMessage"])
        (self.clone / ".megabrain" / "digest.json").write_text(json.dumps({"week": "2000-W01"}))
        later, _ = hook(self.network, "agent", "session-start", {"source": "startup"})
        self.assertIn("weekly digest", later["systemMessage"])

    def test_home_shows_this_week_with_agent_requests(self) -> None:
        self.network.remember("agent", subject="synthetic.studio", summary="The synthetic studio opens at nine.", confidence="inferred")
        result = self.network.command("agent", "browse", None, "--no-open")
        html = Path(result["path"]).read_text()
        self.assertIn('"digest"', html)
        self.assertIn("Go through all of them with an agent", html)
        self.assertIn("Prepare for your agent", html)


if __name__ == "__main__":
    unittest.main()
