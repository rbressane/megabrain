from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock


SOURCE_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SOURCE_ROOT / "skill" / "megabrain" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import megabrain
import vault


SPEC = importlib.util.spec_from_file_location("megabrain_vault_local", SCRIPTS / "vault-local.py")
assert SPEC is not None and SPEC.loader is not None
vault_local = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vault_local)


class FakeTerminal:
    def __init__(self, answers: list[str] | None = None, secrets: list[str] | None = None):
        self.answers = list(answers or [])
        self.secrets = list(secrets or [])
        self.output: list[str] = []

    def ask(self, prompt: str) -> str:
        if not self.answers:
            raise AssertionError(f"unexpected local prompt: {prompt}")
        return self.answers.pop(0)

    def secret(self, prompt: str) -> str:
        if not self.secrets:
            raise AssertionError(f"unexpected protected local prompt: {prompt}")
        return self.secrets.pop(0)

    def show(self, message: str) -> None:
        self.output.append(message)


class VaultLocalControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "brain"
        self.home = Path(self.temporary.name) / "home"
        self.home.mkdir()
        (self.root / "brain" / "memories").mkdir(parents=True)
        (self.root / "brain" / "agents").mkdir()
        (self.root / "brain" / "imports").mkdir()
        (self.root / "megabrain.json").write_text(
            json.dumps(
                {"schema": megabrain.BRAIN_SCHEMA, "protocol_version": 1, "minimum_runtime": "1.0.0"},
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "--initial-branch=main"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Synthetic Owner"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "owner@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "synthetic brain"], cwd=self.root, check=True, capture_output=True)
        self.remote = Path(self.temporary.name) / "remote.git"
        subprocess.run(["git", "init", "--bare", str(self.remote)], check=True, capture_output=True)
        subprocess.run(["git", "remote", "add", "origin", str(self.remote)], cwd=self.root, check=True)
        subprocess.run(["git", "push", "-u", "origin", "main"], cwd=self.root, check=True, capture_output=True)
        self.environment = {"HOME": str(self.home), "MEGABRAIN_ROOT": str(self.root)}
        self.passphrase = "synthetic local passphrase with sufficient length"
        self.secret = "SYN-" + uuid.uuid4().hex

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_local_setup_requires_file_and_agent_path_fails_closed(self) -> None:
        with mock.patch.dict(os.environ, self.environment):
            with self.assertRaises(vault.VaultError) as missing_path:
                megabrain.command_vault(
                    self.root,
                    "setup",
                    {"passphrase": self.passphrase},
                    trusted_local=True,
                )
            self.assertEqual(missing_path.exception.code, "RECOVERY_PATH_REQUIRED")
            self.assertNotIn(
                "brain_id",
                json.loads((self.root / "megabrain.json").read_text(encoding="utf-8")),
            )
            self.assertEqual(
                subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=self.root,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout,
                "",
            )
            with self.assertRaises(vault.VaultError) as agent_denied:
                megabrain.command_vault(
                    self.root,
                    "setup",
                    {"passphrase": self.passphrase, "recovery_path": str(self.home / "recovery.txt")},
                )
            self.assertEqual(agent_denied.exception.code, "LOCAL_ACTION_REQUIRED")
            self.assertNotIn(self.passphrase, agent_denied.exception.message)

            recovery_path = self.home / "recovery.txt"
            setup_terminal = FakeTerminal([str(recovery_path)], [self.passphrase, self.passphrase])
            setup = vault_local.run_local_action(self.root, "setup", setup_terminal)
            self.assertNotIn("recovery_key", setup)
            self.assertNotIn("MBRK1-", "\n".join(setup_terminal.output))
            self.assertEqual(recovery_path.stat().st_mode & 0o777, 0o600)
            status = megabrain.command_vault(self.root, "status", {})
            self.assertFalse(status["ready"])
            vault_local.run_local_action(self.root, "confirm", FakeTerminal())
            self.assertTrue(megabrain.command_vault(self.root, "status", {})["ready"])

    def test_local_put_and_reveal_keep_agent_result_value_free(self) -> None:
        recovery_path = self.home / "recovery.txt"
        resource = "identity://synthetic-subject/passport/example/current"
        with mock.patch.dict(os.environ, self.environment):
            vault_local.run_local_action(
                self.root,
                "setup",
                FakeTerminal([str(recovery_path)], [self.passphrase, self.passphrase]),
            )
            vault_local.run_local_action(self.root, "confirm", FakeTerminal())
            put_terminal = FakeTerminal(
                [resource, "passport", "Synthetic identity", "document_number,expires_on"],
                [self.secret, "2036-01-01", self.passphrase],
            )
            vault_local.run_local_action(self.root, "put", put_terminal)
            self.assertNotIn(self.secret, "\n".join(put_terminal.output))
            with self.assertRaises(vault.VaultError) as denied:
                megabrain.command_vault(
                    self.root,
                    "reveal",
                    {"resource": resource, "fields": ["document_number"], "purpose": "user-request"},
                )
            self.assertEqual(denied.exception.code, "LOCAL_ACTION_REQUIRED")
            self.assertNotIn(self.secret, denied.exception.message)
            reveal_terminal = FakeTerminal(
                [resource, "document_number", "user-request"],
                [self.passphrase],
            )
            result = vault_local.run_local_action(self.root, "reveal", reveal_terminal)
            self.assertEqual(result["fields"]["document_number"], self.secret)
            self.assertIn(self.secret, "\n".join(reveal_terminal.output))


if __name__ == "__main__":
    unittest.main()
