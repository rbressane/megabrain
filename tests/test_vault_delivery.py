from __future__ import annotations

import concurrent.futures
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SOURCE_ROOT / "skill" / "megabrain" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import vault
import vault_delivery


class RecordingAdapter:
    adapter_id = "synthetic.dm"
    host = "local"
    operation = "deliver"

    def __init__(self, receipt: dict | None = None):
        self.received: list[dict] = []
        self.timeouts: list[int | None] = []
        self.receipt = receipt or {"platform": "synthetic-dm", "message_id": "out-1"}

    def deliver(self, fields, *, timeout_seconds=None):
        self.received.append(dict(fields))
        self.timeouts.append(timeout_seconds)
        return dict(self.receipt)


class VaultDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name) / "home"
        self.home.mkdir()
        self.brain = Path(self.temporary.name) / "brain"
        self.brain.mkdir()
        self.brain_id = str(uuid.uuid4())
        self.agent_id = str(uuid.uuid4())
        self.paths = vault.paths_for(self.home, self.brain_id)
        self.store, self.recovery = vault.VaultStore.setup(
            self.paths,
            self.brain_id,
            "synthetic attestation passphrase long enough",
        )
        self.store.confirm_setup()
        self.master = self.store.unlock(passphrase="synthetic attestation passphrase long enough")
        self.identity_resource = "identity://synthetic-subject/passport/current"
        self.credential_resource = "credentials://synthetic-provider/account/current"
        self.identity_secret = "SYN-ID-" + uuid.uuid4().hex
        self.credential_secret = "SYN-TOKEN-" + uuid.uuid4().hex
        self.store.put(
            self.master,
            {
                "logical_id": self.identity_resource,
                "type": "passport",
                "label": "Synthetic passport",
                "fields": {"document_number": self.identity_secret, "expires_on": "2036-01-01"},
            },
        )
        self.store.put(
            self.master,
            {
                "logical_id": self.credential_resource,
                "type": "credential",
                "label": "Synthetic provider credential",
                "fields": {
                    "service": "synthetic",
                    "username": "synthetic-user",
                    "password": self.credential_secret,
                },
            },
        )
        vault.grant_agent(
            self.store,
            self.agent_id,
            self.brain,
            [
                "vault.metadata",
                "identity.metadata",
                "vault.reveal",
                "identity.reveal",
                "credentials.use",
            ],
            ["identity", "credentials"],
        )
        self.authority = vault_delivery.HarnessAuthority.generate()
        self.dm_context = vault_delivery.TrustedContext(
            source_kind="gateway_user",
            platform="telegram",
            chat_type="dm",
            user_id="synthetic-owner",
            chat_id="synthetic-private-chat",
            thread_id="",
            session_id=str(uuid.uuid4()),
            message_id="synthetic-message-1",
            agent_id=self.agent_id,
        )
        self.local_context = vault_delivery.TrustedContext(
            source_kind="local_user",
            platform="local",
            chat_type="local",
            user_id="synthetic-owner",
            chat_id="local-control-plane",
            thread_id="",
            session_id=str(uuid.uuid4()),
            message_id="local-action-1",
            agent_id=self.agent_id,
        )
        self.destinations = [
            {**self.dm_context.stable_destination(), "kind": "private_dm"},
            {**self.local_context.stable_destination(), "kind": "local_secure_ui"},
        ]
        vault_delivery.pair_harness(self.store, self.master, self.authority, self.destinations)
        vault_delivery.set_resource_policy(
            self.store,
            self.master,
            self.identity_resource,
            "private_dm_opt_in",
        )
        self.capability = {
            "capability_id": "synthetic.token-check",
            "adapter_id": "synthetic.token-check",
            "host": "api.example.invalid",
            "operation": "token-check",
            "fields": ["password"],
            "timeout_seconds": 5,
        }
        vault_delivery.register_direct_use_capability(
            self.store,
            self.master,
            self.credential_resource,
            capability_id=self.capability["capability_id"],
            adapter_id=self.capability["adapter_id"],
            host=self.capability["host"],
            operation=self.capability["operation"],
            fields=self.capability["fields"],
            timeout_seconds=self.capability["timeout_seconds"],
        )
        self.prompts: list[dict] = []

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def approve(self, prompt: dict) -> bool:
        self.prompts.append(dict(prompt))
        return True

    def identity_request(self) -> dict:
        return {
            "action": "deliver",
            "resource": self.identity_resource,
            "fields": ["document_number"],
            "purpose": "owner-request",
        }

    def credential_request(self) -> dict:
        return {
            "action": "use",
            "resource": self.credential_resource,
            "fields": ["password"],
            "purpose": "synthetic.token-check",
        }

    def attest_identity(self, *, context=None, authority=None, now=1_000, approve=None):
        return (authority or self.authority).approve_and_attest(
            self.identity_request(),
            context or self.dm_context,
            audience=self.brain_id,
            delivery_policy="private_dm_opt_in",
            safe_label="Synthetic identity document",
            approve=approve or self.approve,
            now=now,
        )[0]

    def attest_credential(self, *, authority=None, now=1_000):
        return (authority or self.authority).approve_and_attest(
            self.credential_request(),
            self.dm_context,
            audience=self.brain_id,
            delivery_policy="direct_use_only",
            safe_label="Synthetic credential",
            capability=self.capability,
            approve=self.approve,
            now=now,
        )[0]

    def test_model_request_schema_rejects_destination_approval_and_secret_fields(self) -> None:
        request = self.identity_request()
        for forbidden in (
            "destination",
            "destination_id",
            "approval",
            "private_context",
            "signature",
            "attestation",
            "value",
            "passphrase",
        ):
            with self.subTest(forbidden=forbidden):
                with self.assertRaises(vault.VaultError) as rejected:
                    vault_delivery.validate_model_request({**request, forbidden: "forbidden"})
                self.assertEqual(rejected.exception.code, "MODEL_REQUEST_MALFORMED")
        with self.assertRaises(vault.VaultError):
            vault_delivery.validate_model_request({**request, "fields": ["document_number", "document_number"]})
        with self.assertRaises(vault.VaultError) as unsafe_resource:
            vault_delivery.validate_model_request({**request, "resource": "identity://safe\nspoof"})
        self.assertEqual(unsafe_resource.exception.code, "MODEL_RESOURCE_INVALID")

    def test_private_dm_delivery_is_exact_approved_one_shot_and_opaque(self) -> None:
        request = self.identity_request()
        envelope = self.attest_identity()
        response = vault_delivery.authorize_and_seal_release(
            self.store,
            self.master,
            request,
            envelope,
            now=1_001,
        )
        serialized_boundaries = json.dumps([request, envelope, response, self.prompts], sort_keys=True)
        self.assertNotIn(self.identity_secret, serialized_boundaries)
        self.assertEqual(self.prompts[0]["fields"], ["document_number"])
        self.assertEqual(self.prompts[0]["purpose"], "owner-request")
        self.assertIn("one-time", self.prompts[0]["warning"])
        adapter = RecordingAdapter()
        receipt = vault_delivery.open_and_deliver(self.authority, response, envelope, adapter)
        self.assertEqual(adapter.received, [{"document_number": self.identity_secret}])
        self.assertNotIn(self.identity_secret, json.dumps(receipt, sort_keys=True))
        with self.assertRaises(vault.VaultError) as replayed:
            vault_delivery.authorize_and_seal_release(self.store, self.master, request, envelope, now=1_002)
        self.assertEqual(replayed.exception.code, "ATTESTATION_REPLAYED")

    def test_broker_returns_only_a_sealed_release_to_the_trusted_harness(self) -> None:
        server = threading.Thread(
            target=vault.serve_broker,
            args=(self.store, self.master, 10),
            daemon=True,
        )
        server.start()
        socket_path = self.paths.runtime / "broker.sock"
        deadline = time.monotonic() + 5
        while not socket_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(socket_path.exists())
        envelope = self.attest_identity(now=int(time.time()))
        response = vault_delivery.request_attested_release(
            self.store,
            self.identity_request(),
            envelope,
        )
        self.assertNotIn(self.identity_secret, json.dumps(response, sort_keys=True))
        adapter = RecordingAdapter()
        receipt = vault_delivery.open_and_deliver(self.authority, response, envelope, adapter)
        self.assertTrue(receipt["delivered"])
        self.assertEqual(adapter.received[0]["document_number"], self.identity_secret)
        vault.lock_broker(self.store)
        server.join(timeout=2)
        self.assertFalse(server.is_alive())

    def test_exact_approval_denial_creates_no_attestation(self) -> None:
        with self.assertRaises(vault.VaultError) as denied:
            self.attest_identity(approve=lambda prompt: False)
        self.assertEqual(denied.exception.code, "APPROVAL_DENIED")
        with self.store.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM attested_requests").fetchone()[0], 0)

    def test_trusted_harness_can_resume_the_same_exact_approval_id(self) -> None:
        approval_id = str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        envelope, prompt = self.authority.approve_and_attest(
            self.identity_request(),
            self.dm_context,
            audience=self.brain_id,
            delivery_policy="private_dm_opt_in",
            safe_label="Synthetic identity document",
            approve=self.approve,
            approval_id=approval_id,
            request_id=request_id,
            now=1_000,
        )
        self.assertEqual(prompt["approval_id"], approval_id)
        self.assertEqual(envelope["approval_id"], approval_id)
        self.assertEqual(prompt["request_id"], request_id)
        self.assertEqual(envelope["request_id"], request_id)

    def test_attestation_tamper_expiry_future_audience_and_key_fail_closed(self) -> None:
        cases = []
        invalid_signature = self.attest_identity()
        invalid_signature["signature"] = vault.b64(os.urandom(64))
        cases.append((invalid_signature, 1_001, "ATTESTATION_SIGNATURE_INVALID"))
        malformed_signature = self.attest_identity()
        malformed_signature["signature"] = "not+canonical/base64"
        cases.append((malformed_signature, 1_001, "ATTESTATION_SIGNATURE_INVALID"))
        wrong_audience = self.attest_identity()
        wrong_audience["audience"] = str(uuid.uuid4())
        cases.append((wrong_audience, 1_001, "ATTESTATION_AUDIENCE_MISMATCH"))
        wrong_issuer = self.attest_identity()
        wrong_issuer["issuer_instance"] = str(uuid.uuid4())
        cases.append((wrong_issuer, 1_001, "HARNESS_KEY_UNKNOWN"))
        wrong_key = self.attest_identity()
        wrong_key["key_id"] = str(uuid.uuid4())
        cases.append((wrong_key, 1_001, "HARNESS_KEY_UNKNOWN"))
        expired = self.attest_identity(now=1_000)
        cases.append((expired, 1_061, "ATTESTATION_EXPIRED"))
        future = self.attest_identity(now=1_100)
        cases.append((future, 1_000, "ATTESTATION_EXPIRED"))
        wrong_destination = self.attest_identity()
        wrong_destination["destination_binding"] = vault.b64(os.urandom(32))
        cases.append((wrong_destination, 1_001, "ATTESTATION_SIGNATURE_INVALID"))
        wrong_fields = self.attest_identity()
        wrong_fields["fields_digest"] = vault.b64(os.urandom(32))
        cases.append((wrong_fields, 1_001, "ATTESTATION_SIGNATURE_INVALID"))
        for envelope, current, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaises(vault.VaultError) as rejected:
                    vault_delivery.authorize_and_seal_release(
                        self.store,
                        self.master,
                        self.identity_request(),
                        envelope,
                        now=current,
                    )
                self.assertEqual(rejected.exception.code, expected)

    def test_group_channel_email_cron_api_webhook_delegated_and_unattended_are_denied(self) -> None:
        cases = (
            ("gateway_user", "telegram", "group"),
            ("gateway_user", "discord", "channel"),
            ("gateway_user", "email", "dm"),
            ("cron", "telegram", "dm"),
            ("api", "api", "api"),
            ("webhook", "webhook", "webhook"),
            ("delegated", "telegram", "dm"),
            ("unattended", "telegram", "dm"),
            ("background", "telegram", "dm"),
            ("gateway_internal", "telegram", "dm"),
        )
        for index, (source_kind, platform, chat_type) in enumerate(cases):
            context = vault_delivery.TrustedContext(
                source_kind=source_kind,
                platform=platform,
                chat_type=chat_type,
                user_id="synthetic-owner",
                chat_id="synthetic-private-chat",
                thread_id="",
                session_id=str(uuid.uuid4()),
                message_id=f"denied-{index}",
                agent_id=self.agent_id,
            )
            envelope = self.attest_identity(context=context)
            with self.subTest(source_kind=source_kind, chat_type=chat_type):
                with self.assertRaises(vault.VaultError) as denied:
                    vault_delivery.authorize_and_seal_release(
                        self.store,
                        self.master,
                        self.identity_request(),
                        envelope,
                        now=1_001,
                    )
                self.assertEqual(denied.exception.code, "DELIVERY_CONTEXT_DENIED")

    def test_owner_destination_mismatch_and_local_policy_mismatch_are_denied(self) -> None:
        other = vault_delivery.TrustedContext(
            **{**self.dm_context.__dict__, "user_id": "different-owner", "message_id": "different-1"}
        )
        envelope = self.attest_identity(context=other)
        with self.assertRaises(vault.VaultError) as denied:
            vault_delivery.authorize_and_seal_release(
                self.store,
                self.master,
                self.identity_request(),
                envelope,
                now=1_001,
            )
        self.assertEqual(denied.exception.code, "DESTINATION_NOT_PAIRED")

        vault_delivery.set_resource_policy(self.store, self.master, self.identity_resource, "local_secure_ui")
        wrong_policy = self.attest_identity()
        with self.assertRaises(vault.VaultError) as mismatch:
            vault_delivery.authorize_and_seal_release(
                self.store,
                self.master,
                self.identity_request(),
                wrong_policy,
                now=1_001,
            )
        self.assertEqual(mismatch.exception.code, "DELIVERY_POLICY_MISMATCH")

    def test_owner_local_secure_ui_delivery(self) -> None:
        vault_delivery.set_resource_policy(self.store, self.master, self.identity_resource, "local_secure_ui")
        envelope = self.authority.approve_and_attest(
            self.identity_request(),
            self.local_context,
            audience=self.brain_id,
            delivery_policy="local_secure_ui",
            safe_label="Synthetic identity",
            approve=self.approve,
            now=1_000,
        )[0]
        sealed = vault_delivery.authorize_and_seal_release(
            self.store,
            self.master,
            self.identity_request(),
            envelope,
            now=1_001,
        )
        adapter = RecordingAdapter({"surface": "local-secure-ui"})
        receipt = vault_delivery.open_and_deliver(self.authority, sealed, envelope, adapter)
        self.assertTrue(receipt["delivered"])
        self.assertEqual(adapter.received[0]["document_number"], self.identity_secret)

    def test_direct_use_capability_has_no_secret_argv_env_or_receipt(self) -> None:
        request = self.credential_request()
        envelope = self.attest_credential()
        response = vault_delivery.authorize_and_seal_release(
            self.store,
            self.master,
            request,
            envelope,
            now=1_001,
        )
        adapter = vault_delivery.SyntheticTokenCheckAdapter()
        before_environment = json.dumps(dict(os.environ), sort_keys=True)
        receipt = vault_delivery.open_and_deliver(self.authority, response, envelope, adapter)
        after_environment = json.dumps(dict(os.environ), sort_keys=True)
        self.assertNotIn(self.credential_secret, before_environment + after_environment)
        self.assertTrue(receipt["receipt"]["authenticated"])
        self.assertEqual(receipt["receipt"]["host"], "api.example.invalid")
        self.assertNotIn(self.credential_secret, json.dumps([request, envelope, response, receipt], sort_keys=True))

    def test_direct_use_revocation_and_adapter_output_leak_fail_closed(self) -> None:
        envelope = self.attest_credential()
        vault_delivery.revoke_direct_use_capability(
            self.store,
            self.master,
            self.credential_resource,
            self.capability["capability_id"],
        )
        with self.assertRaises(vault.VaultError) as revoked:
            vault_delivery.authorize_and_seal_release(
                self.store,
                self.master,
                self.credential_request(),
                envelope,
                now=1_001,
            )
        self.assertEqual(revoked.exception.code, "CAPABILITY_REVOKED")

        vault_delivery.register_direct_use_capability(
            self.store,
            self.master,
            self.credential_resource,
            capability_id=self.capability["capability_id"],
            adapter_id=self.capability["adapter_id"],
            host=self.capability["host"],
            operation=self.capability["operation"],
            fields=self.capability["fields"],
            timeout_seconds=self.capability["timeout_seconds"],
        )
        envelope = self.attest_credential(now=2_000)
        sealed = vault_delivery.authorize_and_seal_release(
            self.store,
            self.master,
            self.credential_request(),
            envelope,
            now=2_001,
        )
        leaking = RecordingAdapter({"bad": self.credential_secret})
        leaking.adapter_id = self.capability["adapter_id"]
        leaking.host = self.capability["host"]
        leaking.operation = self.capability["operation"]
        with self.assertRaises(vault.VaultError) as blocked:
            vault_delivery.open_and_deliver(self.authority, sealed, envelope, leaking)
        self.assertEqual(blocked.exception.code, "ADAPTER_OUTPUT_SECRET")

    def test_direct_use_rejects_wrong_adapter_and_non_owner_origin(self) -> None:
        envelope = self.attest_credential()
        sealed = vault_delivery.authorize_and_seal_release(
            self.store,
            self.master,
            self.credential_request(),
            envelope,
            now=1_001,
        )
        with self.assertRaises(vault.VaultError) as wrong_adapter:
            vault_delivery.open_and_deliver(self.authority, sealed, envelope, RecordingAdapter())
        self.assertEqual(wrong_adapter.exception.code, "ADAPTER_CAPABILITY_MISMATCH")

        wrong_origin = vault_delivery.TrustedContext(
            **{**self.dm_context.__dict__, "source_kind": "local_user", "message_id": "wrong-origin"}
        )
        wrong_envelope = self.authority.approve_and_attest(
            self.credential_request(),
            wrong_origin,
            audience=self.brain_id,
            delivery_policy="direct_use_only",
            safe_label="Synthetic credential",
            capability=self.capability,
            approve=self.approve,
            now=2_000,
        )[0]
        with self.assertRaises(vault.VaultError) as denied:
            vault_delivery.authorize_and_seal_release(
                self.store,
                self.master,
                self.credential_request(),
                wrong_envelope,
                now=2_001,
            )
        self.assertEqual(denied.exception.code, "DIRECT_USE_CONTEXT_DENIED")

    def test_key_rotation_grace_rollback_and_revocation(self) -> None:
        replacement = vault_delivery.HarnessAuthority.generate(self.authority.issuer_instance)
        rotated = vault_delivery.rotate_harness_key(
            self.store,
            self.master,
            self.authority.key_id,
            replacement,
            self.destinations,
            grace_seconds=30,
            now=1_000,
        )
        self.assertEqual(rotated["grace_until"], 1_030)
        old_envelope = self.attest_identity(authority=self.authority, now=1_001)
        old_release = vault_delivery.authorize_and_seal_release(
            self.store,
            self.master,
            self.identity_request(),
            old_envelope,
            now=1_002,
        )
        self.assertTrue(old_release["ok"])
        expired_old = self.attest_identity(authority=self.authority, now=1_031)
        with self.assertRaises(vault.VaultError) as expired:
            vault_delivery.authorize_and_seal_release(
                self.store,
                self.master,
                self.identity_request(),
                expired_old,
                now=1_032,
            )
        self.assertEqual(expired.exception.code, "HARNESS_KEY_EXPIRED")

        rolled_back = vault_delivery.rollback_harness_key(
            self.store,
            self.authority.issuer_instance,
            self.authority.key_id,
            replacement.key_id,
            now=1_020,
        )
        self.assertEqual(rolled_back["restored_key_id"], self.authority.key_id)
        new_envelope = self.attest_identity(authority=replacement, now=1_021)
        with self.assertRaises(vault.VaultError) as revoked:
            vault_delivery.authorize_and_seal_release(
                self.store,
                self.master,
                self.identity_request(),
                new_envelope,
                now=1_022,
            )
        self.assertEqual(revoked.exception.code, "HARNESS_KEY_REVOKED")
        vault_delivery.revoke_harness_key(self.store, self.authority.issuer_instance, self.authority.key_id)
        restored_envelope = self.attest_identity(authority=self.authority, now=1_023)
        with self.assertRaises(vault.VaultError) as final_revoke:
            vault_delivery.authorize_and_seal_release(
                self.store,
                self.master,
                self.identity_request(),
                restored_envelope,
                now=1_024,
            )
        self.assertEqual(final_revoke.exception.code, "HARNESS_KEY_REVOKED")

    def test_concurrent_replay_allows_exactly_one_release(self) -> None:
        envelope = self.attest_identity()

        def attempt():
            try:
                vault_delivery.authorize_and_seal_release(
                    self.store,
                    self.master,
                    self.identity_request(),
                    envelope,
                    now=1_001,
                )
                return "allowed"
            except vault.VaultError as error:
                return error.code

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: attempt(), range(2)))
        self.assertEqual(outcomes.count("allowed"), 1)
        self.assertEqual(outcomes.count("ATTESTATION_REPLAYED"), 1)

    def test_delivery_audit_and_persistent_boundaries_are_value_free(self) -> None:
        envelope = self.attest_identity()
        response = vault_delivery.authorize_and_seal_release(
            self.store,
            self.master,
            self.identity_request(),
            envelope,
            now=1_001,
        )
        audit = vault_delivery.delivery_audit_list(self.store)
        combined = json.dumps([envelope, response, audit], sort_keys=True)
        self.assertNotIn(self.identity_secret, combined)
        self.assertNotIn("synthetic-private-chat", json.dumps(audit, sort_keys=True))
        self.assertNotIn("synthetic-owner", json.dumps(audit, sort_keys=True))
        self.assertNotIn(self.identity_secret.encode(), self.paths.database.read_bytes())

    def test_schema_one_migrates_transactionally_to_delivery_schema(self) -> None:
        tables = (
            "delivery_audit_events",
            "attested_requests",
            "direct_use_capabilities",
            "resource_delivery_policies",
            "harness_destinations",
            "harness_keys",
        )
        connection = sqlite3.connect(self.paths.database)
        connection.execute("PRAGMA foreign_keys=OFF")
        for table in tables:
            connection.execute(f"DROP TABLE {table}")  # nosec B608 - fixed test-only table names.
        connection.execute("UPDATE vault_header SET schema_version=1 WHERE singleton=1")
        connection.execute("PRAGMA user_version=1")
        connection.commit()
        connection.close()
        with self.store.connect() as migrated:
            self.assertEqual(migrated.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(self.store.header(migrated)["schema_version"], 2)
            existing = {
                row[0]
                for row in migrated.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        self.assertTrue(set(tables) <= existing)


if __name__ == "__main__":
    unittest.main()
