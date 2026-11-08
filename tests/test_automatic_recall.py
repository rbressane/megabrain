"""Automatic recall: hooks, visible receipts, faster reads and owner-local activity. Synthetic data only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from tests.test_megabrain import SOURCE_ROOT, BrainNetwork, megabrain_runtime as mb, run
import integrations
import recall


def hook(network: BrainNetwork, name: str, event: str, payload: dict, *, cwd: Path | None = None) -> tuple[dict, subprocess.CompletedProcess[str]]:
    helper = network.homes[name] / f".{network.harnesses[name]}" / "skills" / "megabrain" / "scripts" / "megabrain.py"
    completed = subprocess.run(
        ["python3", str(helper), "hook", event],
        input=json.dumps(payload), text=True, capture_output=True, check=False,
        cwd=str(cwd or network.root),
        env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(network.homes[name])},
    )
    return (json.loads(completed.stdout) if completed.stdout.strip() else {}), completed


def context_of(output: dict) -> str:
    return output.get("hookSpecificOutput", {}).get("additionalContext", "")


def set_sync_age(clone: Path, seconds: float) -> None:
    moment = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    (clone / ".megabrain" / "sync-state.json").write_text(json.dumps({
        "schema": mb.SYNC_STATE_SCHEMA, "synced_at": recall.stamp(moment),
    }), encoding="utf-8")


def activity_text(clone: Path) -> str:
    return "".join(path.read_text(encoding="utf-8") for path in (clone / ".megabrain" / "activity").glob("*.jsonl"))


class FasterReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.network = BrainNetwork()
        self.clone = self.network.clone("agent", "codex")

    def tearDown(self) -> None:
        self.network.close()

    def git_commands(self, function, *args, **kwargs):
        calls: list[list[str]] = []
        original = mb.run

        def recording(command, cwd, **options):
            calls.append(list(command))
            return original(command, cwd, **options)

        with mock.patch.object(mb, "run", side_effect=recording):
            result = function(*args, **kwargs)
        return result, calls

    def test_read_without_local_commits_never_pushes(self) -> None:
        result, calls = self.git_commands(mb.sync_repo, self.clone)
        self.assertTrue(result["synced"])
        self.assertFalse(any(command[:2] == ["git", "push"] for command in calls))
        self.assertTrue(any(command[:2] == ["git", "fetch"] for command in calls))

    def test_pending_local_commit_is_still_pushed(self) -> None:
        remote = run(["git", "remote", "get-url", "origin"], self.clone).stdout.strip()
        run(["git", "remote", "set-url", "origin", str(self.network.root / "missing.git")], self.clone)
        saved = self.network.remember("agent", subject="sync.pending", summary="Synthetic offline write waits to upload.")
        self.assertTrue(saved["created"])
        run(["git", "remote", "set-url", "origin", remote], self.clone)
        result, calls = self.git_commands(mb.sync_repo, self.clone)
        self.assertTrue(result["synced"])
        self.assertTrue(any(command[:2] == ["git", "push"] for command in calls))
        self.assertFalse(mb.pending_local_commits(self.clone))

    def test_validation_runs_once_per_committed_tree(self) -> None:
        with mock.patch.object(mb, "command_validate", wraps=mb.command_validate) as validate:
            mb.sync_repo(self.clone)
            first = validate.call_count
            self.assertLessEqual(first, 1)
            mb.sync_repo(self.clone)
            mb.local_sync_state(self.clone)
            self.assertEqual(validate.call_count, first)
            writer = self.network.clone("writer", "codex")
            self.network.remember("writer", subject="sync.new_tree", summary="A synthetic change creates a new tree.")
            self.assertTrue(writer.exists())
            mb.sync_repo(self.clone)
            self.assertEqual(validate.call_count, first + 1)
            mb.sync_repo(self.clone)
            self.assertEqual(validate.call_count, first + 1)

    def test_validation_cache_is_bound_to_the_runtime_rules(self) -> None:
        mb.sync_repo(self.clone)
        with mock.patch.object(mb, "validator_fingerprint", return_value="different-runtime"), \
                mock.patch.object(mb, "command_validate", wraps=mb.command_validate) as validate:
            mb.sync_repo(self.clone)
            self.assertEqual(validate.call_count, 1)

    def test_invalid_tree_is_never_cached(self) -> None:
        writer = self.network.clone("writer")
        broken = writer / "brain" / "memories" / "2026" / "01" / "broken.md"
        broken.parent.mkdir(parents=True, exist_ok=True)
        broken.write_text("not a memory record\n", encoding="utf-8")
        run(["git", "add", "."], writer)
        run(["git", "commit", "-m", "synthetic invalid record"], writer)
        run(["git", "push", "origin", "HEAD:main"], writer)
        with mock.patch.object(mb, "command_validate", wraps=mb.command_validate) as validate:
            first = mb.sync_repo(self.clone)
            second = mb.sync_repo(self.clone)
        self.assertEqual(first["reason"], "validation_failed")
        self.assertEqual(second["reason"], "validation_failed")
        self.assertEqual(validate.call_count, 2)

    def test_prefetched_remote_is_integrated_without_moving_backwards(self) -> None:
        self.network.clone("writer", "codex")
        newer = self.network.remember("writer", subject="sync.prefetched", summary="A synthetic prefetched change.")
        self.assertTrue(mb.prefetch_remote(self.clone, 10))
        self.assertTrue(mb.sync_repo(self.clone, prefetched=True)["synced"])
        self.assertTrue(any(newer["memory_id"] in path.name for path in (self.clone / "brain" / "memories").rglob("*.md")))
        stale = run(["git", "rev-parse", "HEAD~1"], self.clone).stdout.strip()
        run(["git", "update-ref", mb.PREFETCH_REF, stale], self.clone)
        before = run(["git", "rev-parse", "origin/main"], self.clone).stdout.strip()
        self.assertTrue(mb.sync_repo(self.clone, prefetched=True)["synced"])
        self.assertEqual(run(["git", "rev-parse", "origin/main"], self.clone).stdout.strip(), before)

    def test_failed_prefetch_never_touches_the_network_under_the_lock(self) -> None:
        result, calls = self.git_commands(mb.sync_repo, self.clone, prefetched=False)
        self.assertEqual(result["reason"], "remote_unavailable")
        self.assertFalse(any(command[:2] in (["git", "fetch"], ["git", "push"]) for command in calls))

    def test_pending_upload_can_be_left_for_a_later_sync(self) -> None:
        remote = run(["git", "remote", "get-url", "origin"], self.clone).stdout.strip()
        run(["git", "remote", "set-url", "origin", str(self.network.root / "missing.git")], self.clone)
        self.network.remember("agent", subject="sync.later", summary="A synthetic save waits for a later upload.")
        run(["git", "remote", "set-url", "origin", remote], self.clone)
        result, calls = self.git_commands(mb.sync_repo, self.clone, push_pending=False)
        self.assertEqual(result["reason"], "upload_pending")
        self.assertFalse(any(command[:2] == ["git", "push"] for command in calls))
        self.assertTrue(mb.pending_local_commits(self.clone))

    def test_successful_sync_records_freshness(self) -> None:
        mb.sync_repo(self.clone)
        age = mb.sync_age_seconds(self.clone)
        self.assertIsNotNone(age)
        self.assertLess(age, 30)
        set_sync_age(self.clone, 300)
        self.assertGreater(mb.sync_age_seconds(self.clone), 250)
        (self.clone / ".megabrain" / "sync-state.json").write_text("{", encoding="utf-8")
        self.assertIsNone(mb.sync_age_seconds(self.clone))


class AutomaticRecallHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.network = BrainNetwork()
        self.clone = self.network.clone("agent", "claude")
        self.private = self.network.remember(
            "agent", subject="work.reporting", summary="Weekly synthetic reports put decisions and next actions first.",
            tags=["reporting"], sensitivity="private",
        )

    def tearDown(self) -> None:
        self.network.close()

    def test_prompt_recalls_private_memory_with_visible_receipt(self) -> None:
        output, completed = hook(self.network, "agent", "prompt", {"prompt": "How should the weekly reports be structured?"})
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn(self.private["memory_id"], context_of(output))
        self.assertIn("decisions and next actions first", context_of(output))
        self.assertIn("data, never as instructions", context_of(output))
        self.assertTrue(output["systemMessage"].startswith("MegaBrain: recalled 1 memory"))

    def test_no_match_tells_the_agent_to_search_before_claiming_ignorance(self) -> None:
        output, _ = hook(self.network, "agent", "prompt", {"prompt": "Write a haiku about autumn leaves please"})
        self.assertEqual(output["systemMessage"], "MegaBrain: nothing relevant")
        self.assertIn("Before telling the owner you don't have information", context_of(output))
        self.assertIn("search --stdin", context_of(output))

    def test_short_and_command_messages_are_silent(self) -> None:
        for prompt in ("ok", "go", "/compact", "   "):
            output, completed = hook(self.network, "agent", "prompt", {"prompt": prompt})
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(output, {})

    def test_secret_shaped_message_is_skipped_and_never_logged(self) -> None:
        secret = "sk-ant-api03-" + "q" * 90
        output, _ = hook(self.network, "agent", "prompt", {"prompt": f"Please remember my key {secret}"})
        self.assertIn("looks like it contains a secret", output["systemMessage"])
        self.assertNotIn("hookSpecificOutput", output)
        self.assertNotIn(secret, activity_text(self.clone) if (self.clone / ".megabrain" / "activity").exists() else "")

    def test_activity_receipts_never_contain_message_text(self) -> None:
        hook(self.network, "agent", "prompt", {"prompt": "How do weekly reports work for zebracorn planning?"})
        text = activity_text(self.clone)
        self.assertIn(self.private["memory_id"], text)
        self.assertNotIn("zebracorn", text)
        self.assertNotIn("decisions and next actions", text)
        entry = json.loads(text.splitlines()[-1])
        self.assertEqual(entry["trigger"], "automatic")
        self.assertTrue(entry["found"])

    def test_recent_copy_answers_without_network_or_refresh(self) -> None:
        hook(self.network, "agent", "prompt", {"prompt": "How should the weekly reports be structured?"})
        run(["git", "remote", "set-url", "origin", str(self.network.root / "missing.git")], self.clone)
        output, _ = hook(self.network, "agent", "prompt", {"prompt": "Remind me how weekly reports are structured?"})
        self.assertIn(self.private["memory_id"], context_of(output))
        self.assertNotIn("offline", output["systemMessage"])
        self.assertFalse((self.clone / ".megabrain" / "refresh.json").exists())

    def test_aging_copy_answers_locally_then_refreshes_in_background(self) -> None:
        writer = self.network.clone("writer", "codex")
        self.assertTrue(writer.exists())
        newer = self.network.remember("writer", subject="work.reporting_cadence", summary="Weekly synthetic reports go out on Fridays.", tags=["reporting"])
        set_sync_age(self.clone, 300)
        output, _ = hook(self.network, "agent", "prompt", {"prompt": "When do the weekly reports go out?"})
        self.assertNotIn(newer["memory_id"], context_of(output))
        self.assertIn("local copy 5 min old", output["systemMessage"])
        self.assertTrue((self.clone / ".megabrain" / "refresh.json").exists())
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and (mb.sync_age_seconds(self.clone) or 999) > 60:
            time.sleep(0.2)
        self.assertLess(mb.sync_age_seconds(self.clone), 60)
        output, _ = hook(self.network, "agent", "prompt", {"prompt": "When do the weekly reports go out?"})
        self.assertIn(newer["memory_id"], context_of(output))

    def test_old_copy_synchronizes_before_answering(self) -> None:
        self.network.clone("writer", "codex")
        newer = self.network.remember("writer", subject="work.reporting_cadence", summary="Weekly synthetic reports go out on Fridays.", tags=["reporting"])
        set_sync_age(self.clone, 3600)
        output, _ = hook(self.network, "agent", "prompt", {"prompt": "When do the weekly reports go out?"})
        self.assertIn(newer["memory_id"], context_of(output))
        self.assertNotIn("local copy", output["systemMessage"])

    def test_offline_old_copy_still_answers_and_says_so(self) -> None:
        set_sync_age(self.clone, 3600)
        run(["git", "remote", "set-url", "origin", str(self.network.root / "missing.git")], self.clone)
        output, _ = hook(self.network, "agent", "prompt", {"prompt": "How should the weekly reports be structured?"})
        self.assertIn(self.private["memory_id"], context_of(output))
        self.assertIn("offline, using local copy from 1 h ago", output["systemMessage"])

    def test_conflicting_claims_are_recalled_together(self) -> None:
        self.network.clone("other", "codex")
        first = self.network.remember("agent", subject="person.timezone", summary="The synthetic owner works in Lisbon time.", tags=["timezone"])
        second = self.network.remember("other", subject="person.timezone", summary="The synthetic owner works in Tokyo time.", tags=["timezone"])
        set_sync_age(self.clone, 3600)
        output, _ = hook(self.network, "agent", "prompt", {"prompt": "Which timezone does the owner work in?"})
        self.assertIn(first["memory_id"], context_of(output))
        self.assertIn(second["memory_id"], context_of(output))
        self.assertIn("Conflict on person timezone", context_of(output))
        self.assertIn("conflict needs you", output["systemMessage"])

    def test_session_start_reports_status_and_project_briefing(self) -> None:
        project = self.network.root / "projects" / "zebracorn-gateway"
        project.mkdir(parents=True)
        run(["git", "init", "-q"], project)
        run(["git", "remote", "add", "origin", "https://example.invalid/synthetic/zebracorn-gateway.git"], project)
        memory = self.network.remember("agent", subject="zebracorn.deploys", summary="Zebracorn deploys need a dry run first.", tags=["zebracorn"])
        output, completed = hook(self.network, "agent", "session-start", {"cwd": str(project), "source": "startup"}, cwd=project)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("MegaBrain: connected · synced", output["systemMessage"])
        self.assertIn("memories", output["systemMessage"])
        self.assertIn(memory["memory_id"], context_of(output))
        self.assertIn("search MegaBrain first", context_of(output))
        self.assertNotIn(str(project), context_of(output))

    def test_hook_is_silent_when_this_agent_is_not_connected(self) -> None:
        with tempfile.TemporaryDirectory() as empty_home:
            helper = SOURCE_ROOT / "skill" / "megabrain" / "scripts" / "megabrain.py"
            completed = subprocess.run(
                ["python3", str(helper), "hook", "prompt"], input=json.dumps({"prompt": "What is the weekly report format?"}),
                text=True, capture_output=True, check=False, cwd=empty_home,
                env={**{key: value for key, value in os.environ.items() if key != "MEGABRAIN_ROOT"}, "HOME": empty_home},
            )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout.strip(), "")

    def test_broken_state_never_blocks_the_turn(self) -> None:
        with tempfile.TemporaryDirectory() as broken:
            (Path(broken) / "brain").mkdir()
            helper = SOURCE_ROOT / "skill" / "megabrain" / "scripts" / "megabrain.py"
            completed = subprocess.run(
                ["python3", str(helper), "hook", "prompt"], input=json.dumps({"prompt": "What is the weekly report format?"}),
                text=True, capture_output=True, check=False, cwd=broken,
                env={**os.environ, "HOME": broken, "MEGABRAIN_ROOT": broken},
            )
        self.assertEqual(completed.returncode, 0)
        self.assertIn("MegaBrain:", json.loads(completed.stdout)["systemMessage"])

    def test_activity_and_status_show_that_recall_is_working(self) -> None:
        hook(self.network, "agent", "prompt", {"prompt": "How should the weekly reports be structured?"})
        hook(self.network, "agent", "prompt", {"prompt": "Write a haiku about autumn leaves please"})
        self.network.command("agent", "search", {"query": "weekly reports", "limit": 5}, "--stdin")
        summary = self.network.command("agent", "activity", None)
        self.assertEqual(summary["lookups"], {
            "total": 3, "automatic": 2, "agent_initiated": 1, "found_something": 2, "found_nothing": 1,
        })
        self.assertEqual(summary["top_memories"][0]["id"], self.private["memory_id"])
        self.assertEqual(summary["top_memories"][0]["subject"], "work.reporting")
        self.assertIn("3 lookups in the last 7 days (2 automatic)", summary["message"])
        status = self.network.command("agent", "status", None)
        self.assertEqual(status["automatic_recall"]["hooks"], "installed")
        self.assertEqual(status["automatic_recall"]["automatic_lookups_7d"], 2)

    def test_hooks_never_push_inline_and_hand_uploads_to_the_background(self) -> None:
        remote = run(["git", "remote", "get-url", "origin"], self.clone).stdout.strip()
        run(["git", "remote", "set-url", "origin", str(self.network.root / "missing.git")], self.clone)
        self.network.remember("agent", subject="work.reporting_owner", summary="Synthetic weekly reports are owned by the editor.", tags=["reporting"])
        run(["git", "remote", "set-url", "origin", remote], self.clone)
        set_sync_age(self.clone, 3600)
        output, _ = hook(self.network, "agent", "prompt", {"prompt": "Who owns the weekly reports?"})
        self.assertIn("local saves still uploading", output["systemMessage"])
        self.assertTrue((self.clone / ".megabrain" / "refresh.json").exists())
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and mb.pending_local_commits(self.clone):
            time.sleep(0.2)
        self.assertFalse(mb.pending_local_commits(self.clone))

    def test_activity_hides_private_subjects_without_trusted_context(self) -> None:
        hook(self.network, "agent", "prompt", {"prompt": "How should the weekly reports be structured?"})
        untrusted = recall.summarize(mb, self.clone, 7, None)
        self.assertEqual(untrusted["top_memories"][0]["subject"], "private memory")

    def test_activity_keeps_three_months(self) -> None:
        directory = self.clone / ".megabrain" / "activity"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "2020-01.jsonl").write_text("{}\n", encoding="utf-8")
        recall.record_activity(self.clone, {"event": "prompt", "trigger": "automatic", "found": False})
        self.assertFalse((directory / "2020-01.jsonl").exists())
        self.assertTrue(any(directory.glob("*.jsonl")))


class IntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def settings(self, harness: str = "claude") -> dict:
        return json.loads((self.home / integrations.HOOK_FILES[harness]).read_text(encoding="utf-8"))

    def test_install_preserves_other_settings_and_is_idempotent(self) -> None:
        path = self.home / ".claude" / "settings.json"
        path.parent.mkdir(parents=True)
        foreign = {"type": "command", "command": "synthetic-notify"}
        path.write_text(json.dumps({"model": "synthetic", "hooks": {"UserPromptSubmit": [{"hooks": [foreign]}], "Stop": [{"hooks": [foreign]}]}}), encoding="utf-8")
        first = integrations.install_hooks(self.home, "claude")
        second = integrations.install_hooks(self.home, "claude")
        self.assertEqual((first["hooks"], first["changed"]), ("installed", True))
        self.assertFalse(second["changed"])
        value = self.settings()
        self.assertEqual(value["model"], "synthetic")
        self.assertEqual(value["hooks"]["Stop"], [{"hooks": [foreign]}])
        prompt_groups = value["hooks"]["UserPromptSubmit"]
        self.assertEqual(prompt_groups[0], {"hooks": [foreign]})
        self.assertEqual(len(prompt_groups), 2)
        self.assertIn("megabrain.py hook prompt", prompt_groups[1]["hooks"][0]["command"])
        self.assertEqual(integrations.hook_state(self.home, "claude"), "installed")

    def test_remove_strips_only_megabrain_hooks(self) -> None:
        path = self.home / ".claude" / "settings.json"
        path.parent.mkdir(parents=True)
        foreign = {"type": "command", "command": "synthetic-notify"}
        path.write_text(json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": [foreign]}]}}), encoding="utf-8")
        integrations.install_hooks(self.home, "claude")
        removed = integrations.remove_hooks(self.home, "claude")
        self.assertTrue(removed["changed"])
        self.assertEqual(self.settings(), {"hooks": {"UserPromptSubmit": [{"hooks": [foreign]}]}})
        self.assertEqual(integrations.hook_state(self.home, "claude"), "missing")

    def test_invalid_settings_are_never_overwritten(self) -> None:
        path = self.home / ".claude" / "settings.json"
        path.parent.mkdir(parents=True)
        path.write_text("{ not json", encoding="utf-8")
        result = integrations.install_hooks(self.home, "claude")
        self.assertEqual(result["hooks"], "settings_invalid")
        self.assertEqual(path.read_text(encoding="utf-8"), "{ not json")
        self.assertIn("not valid JSON", integrations.notice("claude", result))

    def test_linked_settings_are_edited_in_place(self) -> None:
        dotfiles = self.home / "dotfiles" / "claude-settings.json"
        dotfiles.parent.mkdir(parents=True)
        dotfiles.write_text("{}", encoding="utf-8")
        link = self.home / ".claude" / "settings.json"
        link.parent.mkdir(parents=True)
        link.symlink_to(dotfiles)
        integrations.install_hooks(self.home, "claude")
        self.assertTrue(link.is_symlink())
        self.assertIn("UserPromptSubmit", json.loads(dotfiles.read_text(encoding="utf-8"))["hooks"])

    def test_hook_command_never_blocks_a_message(self) -> None:
        missing = self.home / ".claude" / "skills" / "megabrain" / "scripts" / "megabrain.py"
        for argument in ("prompt", "session-start"):
            completed = subprocess.run(["sh", "-c", integrations.hook_command(missing, argument)], capture_output=True, text=True)
            self.assertEqual((completed.returncode, completed.stdout), (0, ""))
        old_runtime = self.home / "old" / "skills" / "megabrain" / "scripts" / "megabrain.py"
        old_runtime.parent.mkdir(parents=True)
        old_runtime.write_text("import sys\nsys.stderr.write('invalid choice')\nsys.exit(2)\n", encoding="utf-8")
        completed = subprocess.run(["sh", "-c", integrations.hook_command(old_runtime, "prompt")], capture_output=True, text=True)
        self.assertEqual((completed.returncode, completed.stdout), (0, ""))

    def test_unwritable_settings_are_reported_and_retried_later(self) -> None:
        directory = self.home / ".claude"
        directory.mkdir()
        (directory / "settings.json").write_text("{ not json", encoding="utf-8")
        config = self.home / ".megabrain" / "config.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"schema": "megabrain.user.v1", "clones": {"claude": "/synthetic/clone"}}), encoding="utf-8")
        first = integrations.ensure_current(self.home, "claude")
        self.assertEqual(first["hooks"], "settings_invalid")
        self.assertIsNone(integrations.ensure_current(self.home, "claude"))
        (directory / "settings.json").write_text("{}", encoding="utf-8")
        os.chmod(directory, 0o500)
        try:
            blocked = integrations.ensure_current(self.home, "claude")
            self.assertEqual(blocked["hooks"], "settings_unwritable")
            self.assertIn("cannot be written", blocked["notice"])
            self.assertEqual((directory / "settings.json").read_text(encoding="utf-8"), "{}")
        finally:
            os.chmod(directory, 0o700)
        fixed = integrations.ensure_current(self.home, "claude")
        self.assertEqual(fixed["hooks"], "installed")
        self.assertEqual(integrations.hook_state(self.home, "claude"), "installed")

    def test_conflict_instruction_and_both_claims_survive_the_budget(self) -> None:
        def memory(index: int, conflict: bool = False) -> dict:
            return {"kind": "memory", "citation": {"memory_id": f"m{index}"}, "title": "t" * 80,
                    "excerpt": "e" * 280, "confidence": "confirmed", "created_at": "2026-01-01T00:00:00Z", "conflict": conflict}
        items = [memory(index) for index in range(5)] + [memory(index, True) for index in range(5, 9)]
        groups = [{"subject": "person timezone", "memory_ids": ["m5", "m6", "m7", "m8"]}]
        lines, included = recall.render(items, groups, recall.CONTEXT_CHARACTERS)
        text = "\n".join(lines)
        self.assertTrue(lines[0].startswith("- Conflict on person timezone"))
        for memory_id in ("m5", "m6", "m7", "m8"):
            self.assertIn(f"memory {memory_id} ", text)
        self.assertEqual(len(included), len(lines) - 1)

    def test_codex_hooks_need_owner_trust_and_are_removed_cleanly(self) -> None:
        result = integrations.install_hooks(self.home, "codex")
        self.assertTrue(result["approval_required"])
        self.assertIn("/hooks", integrations.notice("codex", result))
        handler = self.settings("codex")["hooks"]["SessionStart"][0]["hooks"][0]
        self.assertEqual(handler["statusMessage"], "Loading MegaBrain")
        self.assertFalse(integrations.install_hooks(self.home, "codex")["approval_required"])
        integrations.remove_hooks(self.home, "codex")
        self.assertFalse((self.home / ".codex" / "hooks.json").exists())

    def test_hermes_keeps_instruction_driven_recall(self) -> None:
        result = integrations.apply(self.home, "hermes")
        self.assertEqual(result["hooks"], "unsupported")
        text = (self.home / ".hermes" / "SOUL.md").read_text(encoding="utf-8")
        self.assertIn("Before every user request, retrieve private task context", text)
        self.assertIn("search MegaBrain first", text)

    def test_existing_connection_is_upgraded_once_and_disconnected_agents_are_left_alone(self) -> None:
        config = self.home / ".megabrain" / "config.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"schema": "megabrain.user.v1", "clones": {"claude": "/synthetic/clone"}}), encoding="utf-8")
        upgraded = integrations.ensure_current(self.home, "claude")
        self.assertEqual(upgraded["hooks"], "installed")
        self.assertIn("automatically", upgraded["notice"])
        self.assertIsNone(integrations.ensure_current(self.home, "claude"))
        self.assertIsNone(integrations.ensure_current(self.home, "codex"))
        self.assertFalse((self.home / ".codex" / "hooks.json").exists())
        stored = json.loads(config.read_text(encoding="utf-8"))
        self.assertEqual(stored["integrations"]["claude"], {"version": integrations.INTEGRATION_VERSION, "hooks": "installed"})
        self.assertIn("recalls relevant private context automatically", (self.home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_hooks_removed_by_the_owner_stay_removed_on_later_upgrades(self) -> None:
        config = self.home / ".megabrain" / "config.json"
        config.parent.mkdir(parents=True)
        integrations.install_hooks(self.home, "claude")
        integrations.remove_hooks(self.home, "claude")
        config.write_text(json.dumps({
            "schema": "megabrain.user.v1", "clones": {"claude": "/synthetic/clone"},
            "integrations": {"claude": {"version": 0, "hooks": "installed"}},
        }), encoding="utf-8")
        self.assertIsNone(integrations.ensure_current(self.home, "claude"))
        self.assertEqual(integrations.hook_state(self.home, "claude"), "missing")
        stored = json.loads(config.read_text(encoding="utf-8"))["integrations"]["claude"]
        self.assertEqual(stored["hooks"], "removed_by_owner")
        self.assertIn("Before every user request", (self.home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8"))
        integrations.apply(self.home, "claude")
        self.assertEqual(integrations.hook_state(self.home, "claude"), "installed")


class SetupLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.network = BrainNetwork()

    def tearDown(self) -> None:
        self.network.close()

    def test_setup_reports_and_disconnect_removes_automatic_recall(self) -> None:
        self.network.clone("agent")
        completed = self.network.install("agent", "codex")
        result = json.loads(completed.stdout)
        self.assertEqual(result["automatic_recall"]["hooks"], "installed")
        self.assertTrue(result["automatic_recall"]["approval_required"])
        self.assertIn("/hooks", result["automatic_recall"]["notice"])
        home = self.network.homes["agent"]
        self.assertEqual(integrations.hook_state(home, "codex"), "installed")
        run(["python3", str(SOURCE_ROOT / "install.py"), "disconnect", "--harness", "codex", "--home", str(home)], SOURCE_ROOT)
        self.assertFalse((home / ".codex" / "hooks.json").exists())
        self.assertNotIn("MEGABRAIN:START", (home / ".codex" / "AGENTS.md").read_text(encoding="utf-8") if (home / ".codex" / "AGENTS.md").exists() else "")


if __name__ == "__main__":
    unittest.main()
