from __future__ import annotations

import io
import json
import os
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest import mock


SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT / "skill" / "megabrain" / "scripts"))

import vault


def synthetic_item(secret: str) -> dict:
    return {
        "logical_id": "identity://synthetic-subject/passport/example/current",
        "type": "passport",
        "label": "Synthetic identity document",
        "fields": {
            "document_number": secret,
            "issuing_authority": "Synthetic Authority",
            "expires_on": "2036-01-01",
        },
    }


class VaultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "home"
        self.home.mkdir()
        self.brain_id = str(uuid.uuid4())
        self.paths = vault.paths_for(self.home, self.brain_id)
        self.passphrase = "synthetic passphrase with sufficient length"
        self.store, self.recovery = vault.VaultStore.setup(self.paths, self.brain_id, self.passphrase)
        self.store.confirm_setup()
        self.master = self.store.unlock(passphrase=self.passphrase)
        self.secret = "SYN-" + uuid.uuid4().hex

    def tearDown(self) -> None:
        self.temp.cleanup()

    def assertAuthenticationFailure(self, callback) -> None:
        with self.assertRaises(vault.VaultError) as caught:
            callback()
        self.assertEqual(caught.exception.code, "AUTHENTICATION_FAILED")
        if self.secret in caught.exception.message:
            self.fail("Vault error reflected a generated synthetic secret")

    def test_setup_recovery_permissions_and_wrong_unlock_material(self) -> None:
        self.assertEqual(self.paths.root.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.paths.database.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.store.unlock(recovery_key=self.recovery), self.master)
        self.assertAuthenticationFailure(lambda: self.store.unlock(passphrase="wrong passphrase long enough"))
        wrong_recovery = vault.RECOVERY_PREFIX + vault.b64(os.urandom(32))
        self.assertAuthenticationFailure(lambda: self.store.unlock(recovery_key=wrong_recovery))
        rotated_recovery = self.store.rotate_recovery(self.master)
        self.assertAuthenticationFailure(lambda: self.store.unlock(recovery_key=self.recovery))
        self.assertEqual(self.store.unlock(recovery_key=rotated_recovery), self.master)
        with self.assertRaises(vault.VaultError) as caught:
            vault.VaultStore.setup(self.paths, self.brain_id, self.passphrase)
        self.assertEqual(caught.exception.code, "VAULT_EXISTS")
        nacl = vault.crypto()
        with mock.patch.object(nacl, "__version__", "2.0.0"):
            with self.assertRaises(vault.VaultError) as incompatible:
                vault.crypto()
        self.assertEqual(incompatible.exception.code, "VAULT_DEPENDENCY_INCOMPATIBLE")
        with self.store.connect() as connection:
            header = connection.execute("SELECT kdf_memlimit,master_key_nonce FROM vault_header").fetchone()
            connection.execute("UPDATE vault_header SET kdf_memlimit=?", (2**40,))
        with self.assertRaises(vault.VaultError) as malformed_kdf:
            self.store.unlock(passphrase=self.passphrase)
        self.assertEqual(malformed_kdf.exception.code, "VAULT_HEADER_INVALID")
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE vault_header SET kdf_memlimit=?,master_key_nonce=?",
                (header["kdf_memlimit"], b"short"),
            )
        self.assertAuthenticationFailure(lambda: self.store.unlock(passphrase=self.passphrase))

    def test_envelope_encryption_rewrite_tamper_rotation_and_delete(self) -> None:
        created = self.store.put(self.master, synthetic_item(self.secret))
        self.assertTrue(created["created"])
        database_bytes = self.paths.database.read_bytes()
        if self.secret.encode() in database_bytes:
            self.fail("a generated synthetic secret appeared in database bytes")
        metadata = self.store.metadata(self.master, synthetic_item(self.secret)["logical_id"])
        self.assertEqual(metadata["label"], "[protected]")
        self.assertTrue(metadata["masked_fields"]["document_number"].endswith(self.secret[-2:]))
        if self.secret in json.dumps(metadata):
            self.fail("masked metadata exposed a generated synthetic secret")
        short = vault.mask_fields("passport", {"document_number": "Q", "expires_on": "SYNTHETIC-SECRET"})
        self.assertNotIn("Q", short["document_number"])
        self.assertEqual(short["expires_on"], "[protected]")
        hostile_metadata = synthetic_item(self.secret)
        hostile_metadata["label"] = self.secret
        hostile_metadata["fields"]["expires_on"] = self.secret
        self.store.put(self.master, hostile_metadata)
        protected = self.store.metadata(self.master, hostile_metadata["logical_id"])
        self.assertNotIn(self.secret, json.dumps(protected))
        invalid_type = synthetic_item(self.secret)
        invalid_type["type"] = "secret-1234"
        with self.assertRaises(vault.VaultError) as rejected_type:
            self.store.put(self.master, invalid_type)
        self.assertEqual(rejected_type.exception.code, "INVALID_ITEM")
        invalid_field = synthetic_item(self.secret)
        invalid_field["fields"][self.secret] = "x"
        with self.assertRaises(vault.VaultError) as rejected_field:
            self.store.put(self.master, invalid_field)
        self.assertEqual(rejected_field.exception.code, "INVALID_ITEM_SCHEMA")
        revealed = self.store.reveal(self.master, synthetic_item(self.secret)["logical_id"], ["document_number"])
        if revealed["fields"]["document_number"] != self.secret:
            self.fail("revealed field did not match the generated secret")

        with self.store.connect() as connection:
            first = connection.execute("SELECT * FROM items WHERE item_id=?", (created["item_id"],)).fetchone()
            first_ciphertext = bytes(first["encrypted_payload"])
            first_nonce = bytes(first["payload_nonce"])
            first_wrapped_key = bytes(first["wrapped_item_key"])
        rewritten = synthetic_item(self.secret)
        rewritten["label"] = "Corrected synthetic identity document"
        self.store.put(self.master, rewritten)
        with self.store.connect() as connection:
            second = connection.execute("SELECT * FROM items WHERE item_id=?", (created["item_id"],)).fetchone()
            self.assertNotEqual(bytes(second["encrypted_payload"]), first_ciphertext)
            self.assertNotEqual(bytes(second["payload_nonce"]), first_nonce)
            original = bytes(second["encrypted_payload"])
            tampered = bytearray(original)
            tampered[-1] ^= 1
            connection.execute("UPDATE items SET encrypted_payload=? WHERE item_id=?", (bytes(tampered), created["item_id"]))
        self.assertAuthenticationFailure(
            lambda: self.store.reveal(self.master, rewritten["logical_id"], ["document_number"])
        )
        with self.store.connect() as connection:
            connection.execute("UPDATE items SET encrypted_payload=? WHERE item_id=?", (original, created["item_id"]))
            payload_before_rotation = bytes(
                connection.execute("SELECT encrypted_payload FROM items WHERE item_id=?", (created["item_id"],)).fetchone()[0]
            )
        for column in ("payload_nonce", "wrapped_item_key", "key_nonce"):
            baseline = bytes(second[column])
            changed = bytearray(baseline)
            changed[-1] ^= 1
            with self.store.connect() as connection:
                connection.execute(f"UPDATE items SET {column}=? WHERE item_id=?", (bytes(changed), created["item_id"]))
            self.assertAuthenticationFailure(
                lambda: self.store.reveal(self.master, rewritten["logical_id"], ["document_number"])
            )
            with self.store.connect() as connection:
                connection.execute(f"UPDATE items SET {column}=? WHERE item_id=?", (baseline, created["item_id"]))
        with self.store.connect() as connection:
            baseline_nonce = connection.execute(
                "SELECT key_nonce FROM items WHERE item_id=?", (created["item_id"],)
            ).fetchone()[0]
            connection.execute("UPDATE items SET key_nonce=NULL WHERE item_id=?", (created["item_id"],))
        self.assertAuthenticationFailure(
            lambda: self.store.reveal(self.master, rewritten["logical_id"], ["document_number"])
        )
        with self.store.connect() as connection:
            connection.execute("UPDATE items SET key_nonce=? WHERE item_id=?", (baseline_nonce, created["item_id"]))
        with self.store.connect() as connection:
            connection.execute("UPDATE items SET item_version=item_version+1 WHERE item_id=?", (created["item_id"],))
        self.assertAuthenticationFailure(
            lambda: self.store.reveal(self.master, rewritten["logical_id"], ["document_number"])
        )
        with self.store.connect() as connection:
            connection.execute("UPDATE items SET item_version=item_version-1 WHERE item_id=?", (created["item_id"],))

        other = synthetic_item("SYN-" + uuid.uuid4().hex)
        other["logical_id"] = "identity://synthetic-subject/passport/example/previous"
        other_created = self.store.put(self.master, other)
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM items WHERE item_id IN (?,?)", (created["item_id"], other_created["item_id"])
            ).fetchall()
        unwrapped = [
            vault.decrypt(
                self.master,
                bytes(row["wrapped_item_key"]),
                bytes(row["key_nonce"]),
                self.store.item_aad(row["item_id"], bytes(row["resource_digest"]), row["item_version"], "key"),
            )
            for row in rows
        ]
        self.assertNotEqual(unwrapped[0], unwrapped[1])
        new_passphrase = "a different synthetic passphrase with length"
        self.store.rotate_passphrase(self.master, new_passphrase)
        self.assertAuthenticationFailure(lambda: self.store.unlock(passphrase=self.passphrase))
        self.assertEqual(self.store.unlock(passphrase=new_passphrase), self.master)
        with self.store.connect() as connection:
            payload_after_rotation = bytes(
                connection.execute("SELECT encrypted_payload FROM items WHERE item_id=?", (created["item_id"],)).fetchone()[0]
            )
        self.assertEqual(payload_before_rotation, payload_after_rotation)
        self.assertNotEqual(first_wrapped_key, bytes(second["wrapped_item_key"]))

        deleted = self.store.delete(self.master, rewritten["logical_id"])
        self.assertTrue(deleted["deleted"])
        with self.assertRaises(vault.VaultError) as caught:
            self.store.reveal(self.master, rewritten["logical_id"], ["document_number"])
        self.assertEqual(caught.exception.code, "ITEM_NOT_FOUND")

    def test_attachment_encryption_integrity_orphans_and_permissions(self) -> None:
        item = synthetic_item(self.secret)
        self.store.put(self.master, item)
        plaintext = ("generated-" + uuid.uuid4().hex).encode() * 1000
        source = Path(self.temp.name) / "synthetic-input.bin"
        source.write_bytes(plaintext)
        attached = vault.add_attachment(self.store, self.master, item["logical_id"], source)
        with self.store.connect() as connection:
            row = connection.execute("SELECT * FROM attachments WHERE attachment_id=?", (attached["attachment_id"],)).fetchone()
        blob = self.paths.attachments / row["blob_name"]
        self.assertEqual(blob.stat().st_mode & 0o777, 0o600)
        if plaintext in blob.read_bytes():
            self.fail("generated attachment plaintext appeared in ciphertext bytes")
        output = io.BytesIO()
        vault.extract_attachment(self.store, self.master, attached["attachment_id"], output)
        if output.getvalue() != plaintext:
            self.fail("decrypted attachment did not match the generated source")
        content = bytearray(blob.read_bytes())
        content[-1] ^= 1
        blob.write_bytes(content)
        rejected_output = io.BytesIO()
        audits_before = len(self.store.audit_list(500)["events"])
        with self.assertRaises(vault.VaultError) as caught:
            vault.extract_attachment(self.store, self.master, attached["attachment_id"], rejected_output)
        self.assertIn(caught.exception.code, {"AUTHENTICATION_FAILED", "ATTACHMENT_CORRUPT"})
        self.assertEqual(rejected_output.getvalue(), b"")
        audits_after = self.store.audit_list(500)["events"]
        self.assertGreater(len(audits_after), audits_before)
        self.assertEqual(audits_after[0]["outcome"], "denied")
        orphan = self.paths.attachments / "orphan.mbva"
        orphan.write_bytes(b"not sensitive")
        os.chmod(orphan, 0o600)
        report = vault.doctor(self.store)
        self.assertEqual(report["orphan_count"], 1)

    def test_signed_policy_private_context_replay_staleness_tamper_and_revoke(self) -> None:
        item = synthetic_item(self.secret)
        self.store.put(self.master, item)
        brain_root = Path(self.temp.name) / "brain"
        brain_root.mkdir()
        agent_id = str(uuid.uuid4())
        vault.grant_agent(
            self.store,
            agent_id,
            brain_root,
            ["vault.metadata", "identity.metadata", "vault.reveal", "identity.reveal"],
            ["identity"],
        )
        metadata_request = vault.signed_request(
            brain_root,
            {"method": "metadata", "resource": item["logical_id"], "purpose": "locate", "context": {"kind": "unknown"}},
        )
        allowed = vault.authorize_request(self.store, self.master, metadata_request)
        self.assertEqual(allowed["method"], "metadata")
        with self.assertRaises(vault.VaultError) as replayed:
            vault.authorize_request(self.store, self.master, metadata_request)
        self.assertEqual(replayed.exception.code, "REPLAY_REJECTED")

        for context in ({"kind": "unknown"}, {"kind": "group"}, {"kind": "private"}):
            request = vault.signed_request(
                brain_root,
                {"method": "reveal", "resource": item["logical_id"], "fields": ["document_number"], "purpose": "user-request", "context": context},
            )
            with self.assertRaises(vault.VaultError) as denied:
                vault.authorize_request(self.store, self.master, request)
            self.assertEqual(denied.exception.code, "PRIVATE_CONTEXT_UNATTESTED")

        stale = vault.signed_request(
            brain_root,
            {"method": "metadata", "resource": item["logical_id"], "purpose": "locate", "context": {"kind": "private"}},
        )
        with self.assertRaises(vault.VaultError) as stale_error:
            vault.authorize_request(self.store, self.master, stale, now=stale["timestamp"] + 61)
        self.assertEqual(stale_error.exception.code, "STALE_REQUEST")
        modified = vault.signed_request(
            brain_root,
            {"method": "metadata", "resource": item["logical_id"], "purpose": "locate", "context": {"kind": "private"}},
        )
        modified["fields"] = ["document_number"]
        with self.assertRaises(vault.VaultError) as modified_error:
            vault.authorize_request(self.store, self.master, modified)
        self.assertEqual(modified_error.exception.code, "SIGNATURE_INVALID")

        vault.revoke_agent(self.store, agent_id)
        revoked = vault.signed_request(
            brain_root,
            {"method": "metadata", "resource": item["logical_id"], "purpose": "locate", "context": {"kind": "private"}},
        )
        with self.assertRaises(vault.VaultError) as revoked_error:
            vault.authorize_request(self.store, self.master, revoked)
        self.assertEqual(revoked_error.exception.code, "AGENT_REVOKED")
        audit = self.store.audit_list(100)
        self.assertGreaterEqual(len(audit["events"]), 9)
        if self.secret in json.dumps(audit):
            self.fail("audit output exposed a generated synthetic secret")

    def test_broker_backup_clean_restore_and_wrong_passphrase(self) -> None:
        item = synthetic_item(self.secret)
        self.store.put(self.master, item)
        attachment_plaintext = ("backup-" + uuid.uuid4().hex).encode()
        attachment_source = Path(self.temp.name) / "backup-source.bin"
        attachment_source.write_bytes(attachment_plaintext)
        attached = vault.add_attachment(self.store, self.master, item["logical_id"], attachment_source)
        brain_root = Path(self.temp.name) / "broker-brain"
        brain_root.mkdir()
        agent_id = str(uuid.uuid4())
        vault.grant_agent(
            self.store,
            agent_id,
            brain_root,
            ["vault.metadata", "identity.metadata"],
            ["identity"],
        )
        server = threading.Thread(target=vault.serve_broker, args=(self.store, self.master, 30), daemon=True)
        server.start()
        socket_path = self.paths.runtime / "broker.sock"
        deadline = time.monotonic() + 5
        while not socket_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        request = vault.signed_request(
            brain_root,
            {"method": "metadata", "resource": item["logical_id"], "purpose": "locate", "context": {"kind": "private"}},
        )
        result = vault.broker_socket_request(socket_path, request)
        if self.secret in json.dumps(result):
            self.fail("broker metadata exposed a generated synthetic secret")
        vault.lock_broker(self.store)
        server.join(timeout=5)
        self.assertFalse(server.is_alive())

        backup = Path(self.temp.name) / "portable.mbvault"
        lock_held = threading.Event()
        release_lock = threading.Event()
        export_errors: list[Exception] = []

        def hold_mutations() -> None:
            with self.store.mutation_lock():
                lock_held.set()
                release_lock.wait(timeout=5)

        def run_export() -> None:
            try:
                vault.export_backup(self.store, backup)
            except Exception as error:  # pragma: no cover - asserted below
                export_errors.append(error)

        holder = threading.Thread(target=hold_mutations)
        holder.start()
        self.assertTrue(lock_held.wait(timeout=2))
        exporter = threading.Thread(target=run_export)
        exporter.start()
        time.sleep(0.05)
        self.assertFalse(backup.exists())
        release_lock.set()
        holder.join(timeout=2)
        exporter.join(timeout=5)
        self.assertFalse(export_errors)
        self.assertTrue(backup.exists())
        if self.secret.encode() in backup.read_bytes():
            self.fail("a generated synthetic secret appeared in backup bytes")
        wrong_home = Path(self.temp.name) / "wrong-home"
        wrong_paths = vault.paths_for(wrong_home, self.brain_id)
        with self.assertRaises(vault.VaultError) as wrong:
            vault.restore_backup(backup, wrong_paths, passphrase="wrong passphrase long enough")
        self.assertEqual(wrong.exception.code, "AUTHENTICATION_FAILED")
        self.assertFalse(wrong_paths.root.exists())
        compressed = Path(self.temp.name) / "compressed.mbvault"
        with zipfile.ZipFile(compressed, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", b"{}")
        compressed_paths = vault.paths_for(Path(self.temp.name) / "compressed-home", self.brain_id)
        with self.assertRaises(vault.VaultError) as bounded:
            vault.restore_backup(compressed, compressed_paths, passphrase=self.passphrase)
        self.assertEqual(bounded.exception.code, "BACKUP_INVALID")
        self.assertFalse(compressed_paths.root.exists())
        restored_home = Path(self.temp.name) / "restored-home"
        restored_paths = vault.paths_for(restored_home, self.brain_id)
        restored = vault.restore_backup(backup, restored_paths, recovery_key=self.recovery)
        self.assertEqual(restored["items"], 1)
        second = vault.VaultStore(restored_paths)
        second_master = second.unlock(recovery_key=self.recovery)
        recovered = second.reveal(second_master, item["logical_id"], ["document_number"])
        if recovered["fields"]["document_number"] != self.secret:
            self.fail("restored field did not match the generated secret")
        recovered_attachment = io.BytesIO()
        vault.extract_attachment(second, second_master, attached["attachment_id"], recovered_attachment)
        if recovered_attachment.getvalue() != attachment_plaintext:
            self.fail("restored attachment did not match the generated source")

    def test_broker_slow_client_cannot_bypass_idle_lock_or_duplicate_start(self) -> None:
        server = threading.Thread(target=vault.serve_broker, args=(self.store, self.master, 5), daemon=True)
        server.start()
        socket_path = self.paths.runtime / "broker.sock"
        deadline = time.monotonic() + 5
        while not socket_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(socket_path.exists())
        with self.assertRaises(vault.VaultError) as duplicate:
            vault.serve_broker(self.store, self.master, 5)
        self.assertEqual(duplicate.exception.code, "BROKER_ALREADY_RUNNING")
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(vault.broker_socket_path(self.paths.runtime)))
        client.sendall(b'{"schema":')
        deadline = time.monotonic() + 7
        while server.is_alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        client.close()
        server.join(timeout=1)
        self.assertFalse(server.is_alive())
        self.assertFalse(socket_path.exists())


class VaultRuntimePathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_long_socket_fallback_rejects_precreated_symlink(self) -> None:
        temporary_root = Path(self.temp.name) / "synthetic-tmp"
        temporary_root.mkdir()
        target = Path(self.temp.name) / "unrelated-target"
        target.mkdir(mode=0o755)
        marker = target / "marker.txt"
        marker.write_text("unchanged", encoding="utf-8")
        predictable = temporary_root / f"megabrain-vault-{os.getuid()}"
        predictable.symlink_to(target, target_is_directory=True)
        long_runtime = Path(self.temp.name) / ("long-runtime-segment-" * 8)
        with self.assertRaises(vault.VaultError) as rejected:
            vault.broker_socket_path(long_runtime, temporary_root=temporary_root)
        self.assertEqual(rejected.exception.code, "VAULT_RUNTIME_PATH_UNSAFE")
        self.assertTrue(predictable.is_symlink())
        self.assertEqual(marker.read_text(encoding="utf-8"), "unchanged")
        self.assertEqual(target.stat().st_mode & 0o777, 0o755)

    def test_long_socket_fallback_rejects_unsafe_existing_mode(self) -> None:
        temporary_root = Path(self.temp.name) / "synthetic-tmp"
        temporary_root.mkdir()
        predictable = temporary_root / f"megabrain-vault-{os.getuid()}"
        predictable.mkdir(mode=0o755)
        long_runtime = Path(self.temp.name) / ("long-runtime-segment-" * 8)
        with self.assertRaises(vault.VaultError) as rejected:
            vault.broker_socket_path(long_runtime, temporary_root=temporary_root)
        self.assertEqual(rejected.exception.code, "VAULT_RUNTIME_PATH_UNSAFE")
        self.assertEqual(predictable.stat().st_mode & 0o777, 0o755)


if __name__ == "__main__":
    unittest.main()
