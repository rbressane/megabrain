"""Shared agent activity for the Today page. Synthetic data only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unittest
from unittest import mock

from tests.test_megabrain import BrainNetwork, megabrain_runtime as mb, run
import activity
import live_home
import recall


def receipt(**overrides) -> dict:
    value = {
        "schema": recall.ACTIVITY_SCHEMA, "at": recall.stamp(datetime.now(timezone.utc)), "event": "prompt",
        "trigger": "automatic", "mode": "local", "agent": "claude", "found": True,
        "memories": ["00000000-0000-4000-8000-00000000000a"], "resources": [], "conflicts": 0, "duration_ms": 12,
    }
    value.update(overrides)
    return value


class SharedActivityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.network = BrainNetwork()
        self.first = self.network.clone("first", "claude")
        self.second = self.network.clone("second", "codex")
        self.memory = self.network.remember("first", subject="work.reporting", summary="Synthetic reports lead with decisions.", tags=["reporting"])
        self.network.command("first", "search", {"query": "synthetic reports zebracorn", "limit": 5}, "--stdin")
        self.network.command("second", "search", {"query": "synthetic reports", "limit": 5}, "--stdin")

    def tearDown(self) -> None:
        self.network.close()

    def agent_id(self, clone: Path) -> str:
        return str(mb.load_identity(clone)["id"])

    def branch_paths(self, clone: Path) -> list[str]:
        run(["git", "fetch", "origin", f"+refs/heads/{activity.BRANCH}:refs/test/activity"], clone)
        return run(["git", "ls-tree", "-r", "--name-only", "refs/test/activity"], clone).stdout.split()

    def test_publish_writes_only_this_agents_value_free_receipts(self) -> None:
        result = activity.publish(mb, self.first, force=True)
        self.assertTrue(result["published"])
        paths = self.branch_paths(self.first)
        self.assertTrue(paths)
        self.assertTrue(all(path.startswith(f"activity/{self.agent_id(self.first)}/") for path in paths))
        content = run(["git", "show", f"refs/test/activity:{paths[0]}"], self.first).stdout
        self.assertNotIn("zebracorn", content)
        self.assertNotIn("decisions", content)
        self.assertIn(self.memory["memory_id"], content)
        self.assertEqual(run(["git", "rev-list", "--count", "refs/test/activity"], self.first).stdout.strip(), "1")
        self.assertEqual(run(["git", "status", "--porcelain"], self.first).stdout, "")

    def test_two_agents_publish_without_overwriting_each_other(self) -> None:
        activity.publish(mb, self.first, force=True)
        activity.publish(mb, self.second, force=True)
        self.network.command("first", "search", {"query": "synthetic reports again", "limit": 5}, "--stdin")
        activity.publish(mb, self.first, force=True)
        agents = {path.split("/")[1] for path in self.branch_paths(self.first)}
        self.assertEqual(agents, {self.agent_id(self.first), self.agent_id(self.second)})

    def test_concurrent_publish_rebuilds_instead_of_overwriting(self) -> None:
        activity.publish(mb, self.first, force=True)
        activity.fetch_remote(self.second, 10)
        stale = run(["git", "rev-parse", activity.REMOTE_REF], self.second).stdout.strip()
        self.network.command("first", "search", {"query": "synthetic reports later", "limit": 5}, "--stdin")
        activity.publish(mb, self.first, force=True)  # The branch moves after the second agent's fetch.
        real_fetch = activity.fetch_remote
        calls = []

        def stale_then_real(root, timeout, ref=activity.REMOTE_REF):
            calls.append(root)
            if len(calls) == 1:
                run(["git", "update-ref", ref, stale], root)
                return "fetched"
            return real_fetch(root, timeout, ref)

        with mock.patch.object(activity, "fetch_remote", side_effect=stale_then_real):
            result = activity.publish(mb, self.second, force=True)
        self.assertTrue(result["published"])
        self.assertEqual(len(calls), 2)
        agents = {path.split("/")[1] for path in self.branch_paths(self.second)}
        self.assertEqual(agents, {self.agent_id(self.first), self.agent_id(self.second)})

    def test_publish_is_throttled_and_skips_unchanged_receipts(self) -> None:
        self.assertTrue(activity.publish(mb, self.first)["published"])
        self.assertEqual(activity.publish(mb, self.first)["reason"], "unchanged")
        self.network.command("first", "search", {"query": "synthetic reports once more", "limit": 5}, "--stdin")
        self.assertEqual(activity.publish(mb, self.first)["reason"], "throttled")
        later = datetime.now(timezone.utc) + timedelta(seconds=activity.PUBLISH_INTERVAL_SECONDS + 5)
        self.assertTrue(activity.publish(mb, self.first, now=later)["published"])

    def test_home_combines_shared_and_local_activity(self) -> None:
        activity.publish(mb, self.second, force=True)
        activity.fetch_remote(self.first, 10)
        visible = {self.memory["memory_id"]}
        summary = activity.home_activity(mb, self.first, visible_ids=visible, include_local=True)
        agents = {item["agent_id"]: item for item in summary["agents"]}
        self.assertEqual(set(agents), {self.agent_id(self.first), self.agent_id(self.second)})
        self.assertEqual(summary["totals_7d"]["lookups"], 2)
        self.assertEqual(summary["top_memories"][0]["id"], self.memory["memory_id"])
        self.assertEqual(summary["memories_used_7d"], 1)
        hidden = activity.home_activity(mb, self.first, visible_ids=set(), include_local=True)
        self.assertEqual(hidden["top_memories"], [])
        self.assertEqual(hidden["memories_used_7d"], 0)

    def test_untrusted_receipts_from_the_branch_are_validated(self) -> None:
        bad_agent = "00000000-0000-4000-8000-0000000000ff"
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        lines = [
            json.dumps(receipt()),
            json.dumps(receipt(prompt="Synthetic leaked message text")),
            json.dumps(receipt(memories=["not-a-uuid"])),
            json.dumps(receipt(event="exfiltrate")),
            "not json",
        ]
        work = self.network.root / "crafted"
        work.mkdir()
        (work / "day.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        blob = run(["git", "hash-object", "-w", str(work / "day.jsonl")], self.second).stdout.strip()
        index = work / "index"
        env = {"GIT_INDEX_FILE": str(index)}
        run(["git", "update-index", "--add", "--cacheinfo", f"100644,{blob},activity/{bad_agent}/{today}.jsonl"], self.second, env=env)
        tree = run(["git", "write-tree"], self.second, env=env).stdout.strip()
        commit = run(["git", "commit-tree", tree, "-m", "synthetic crafted activity"], self.second).stdout.strip()
        run(["git", "push", "origin", f"{commit}:refs/heads/{activity.BRANCH}"], self.second)
        activity.fetch_remote(self.first, 10)
        summary = activity.home_activity(mb, self.first, visible_ids=set(), include_local=False)
        self.assertEqual(summary["agents"][0]["agent_id"], bad_agent)
        self.assertEqual(summary["agents"][0]["lookups_7d"], 2)  # The plain line and the one with an unknown field.
        self.assertNotIn("leaked", json.dumps(summary))

    def test_receipt_validation_rejects_odd_values(self) -> None:
        self.assertIsNotNone(activity.valid_receipt(receipt()))
        self.assertNotIn("prompt", activity.valid_receipt(receipt(prompt="text")))
        for broken in (receipt(found="yes"), receipt(agent="other"), receipt(conflicts=-1), receipt(at="yesterday"),
                       receipt(resources=[{"uri": "https://example.invalid", "revision_id": "x"}]), receipt(schema="other")):
            self.assertIsNone(activity.valid_receipt(broken))

    def test_browse_publishes_and_embeds_activity(self) -> None:
        activity.publish(mb, self.second, force=True)
        browsed = self.network.command("first", "browse", None, "--no-open")
        html = Path(browsed["path"]).read_text(encoding="utf-8")
        self.assertIn('"activity": {', html)
        self.assertIn(self.agent_id(self.second), html)
        agents = {path.split("/")[1] for path in self.branch_paths(self.first)}
        self.assertIn(self.agent_id(self.first), agents)


class LiveHomeActivityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.network = BrainNetwork()
        self.writer = self.network.clone("writer", "claude")
        self.private = self.network.remember("writer", subject="work.private_cadence", summary="Synthetic private cadence.", sensitivity="private", tags=["cadence"])
        self.general = self.network.remember("writer", subject="work.general_cadence", summary="Synthetic general cadence.", tags=["cadence"])
        self.network.command("writer", "search", {"query": "synthetic cadence", "limit": 5}, "--stdin")
        activity.publish(mb, self.writer, force=True)
        self.root = self.network.clone("viewer")
        self.view = live_home.LiveView(self.root)

    def tearDown(self) -> None:
        self.network.close()

    def test_live_home_shows_activity_and_names_only_general_memories(self) -> None:
        self.view.refresh()
        data = self.view.data()["data"]
        self.assertTrue(data["activity"]["available"])
        self.assertEqual(data["activity"]["totals_7d"]["lookups"], 1)
        named = {item["id"] for item in data["activity"]["top_memories"]}
        self.assertIn(self.general["memory_id"], named)
        self.assertNotIn(self.private["memory_id"], named)
        commit = self.view.projection.commit
        self.network.command("writer", "search", {"query": "synthetic cadence again", "limit": 5}, "--stdin")
        activity.publish(mb, self.writer, force=True)
        self.view.refresh()
        self.assertEqual(self.view.projection.commit, commit)
        self.assertEqual(self.view.data()["data"]["activity"]["totals_7d"]["lookups"], 2)


if __name__ == "__main__":
    unittest.main()
