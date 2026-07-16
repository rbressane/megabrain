#!/usr/bin/env python3
"""Trusted-harness attestation and opaque MegaBrain Vault delivery.

The model supplies only a small value-free request. A paired harness constructs
and signs the destination context after an exact owner approval. Vault validates
that envelope, consumes it once, and seals selected plaintext to the harness key.
The sealed payload is never a model tool result; a trusted adapter opens it and
receives the selected fields directly.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping, MutableMapping, Protocol

import vault


ATTESTATION_SCHEMA = "megabrain.vault-attestation.v1"
RELEASE_SCHEMA = "megabrain.vault-sealed-release.v1"
MAX_ATTESTATION_TTL = 60
MAX_ATTESTATION_FUTURE_SKEW = 5
MODEL_ACTIONS = {"locate", "metadata", "deliver", "use"}
DELIVERY_POLICIES = {
    "metadata_only",
    "local_secure_ui",
    "private_dm_opt_in",
    "direct_use_only",
    "never_reveal",
}
DENIED_SOURCE_KINDS = {
    "gateway_internal",
    "api",
    "cron",
    "webhook",
    "delegated",
    "unattended",
    "background",
    "system",
    "unknown",
}
DENIED_CHAT_TYPES = {"group", "channel", "forum", "email", "webhook", "cron", "api"}
MODEL_REQUEST_KEYS = {"action", "resource", "fields", "purpose"}
ATTESTATION_KEYS = {
    "schema",
    "issuer_instance",
    "key_id",
    "audience",
    "request_id",
    "nonce",
    "issued_at",
    "expires_at",
    "agent_id",
    "session_id",
    "message_id",
    "source_kind",
    "platform",
    "chat_type",
    "user_id",
    "chat_id",
    "thread_id",
    "action",
    "resource_digest",
    "fields_digest",
    "purpose",
    "approval_id",
    "delivery_policy",
    "capability_id",
    "destination_binding",
    "signature",
}
PURPOSE_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
FIELD_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}")
RESOURCE_PATTERN = re.compile(r"[a-z][a-z0-9+.-]{0,31}://[A-Za-z0-9][A-Za-z0-9._~/-]{0,477}")
HOST_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?")
ENCODED_PATTERN = re.compile(r"[A-Za-z0-9_-]+")


def _uuid(value: Any, code: str) -> str:
    if not isinstance(value, str):
        raise vault.VaultError(code, "The trusted delivery identifier is invalid.")
    try:
        parsed = uuid.UUID(value)
    except ValueError as error:
        raise vault.VaultError(code, "The trusted delivery identifier is invalid.") from error
    if str(parsed) != value:
        raise vault.VaultError(code, "The trusted delivery identifier is invalid.")
    return value


def _text(value: Any, *, maximum: int = 512, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > maximum or (not allow_empty and not value):
        raise vault.VaultError("ATTESTATION_MALFORMED", "The trusted delivery envelope is malformed.")
    return value


def _digest(key: bytes, label: str, value: Any) -> str:
    return vault.b64(hmac.new(key, label.encode() + b"\0" + vault.canonical(value), hashlib.sha256).digest())


def _unb64_exact(value: Any, size: int, code: str) -> bytes:
    if not isinstance(value, str) or ENCODED_PATTERN.fullmatch(value) is None:
        raise vault.VaultError(code, "The trusted delivery encoding is invalid.")
    try:
        decoded = vault.unb64(value)
    except vault.VaultError as error:
        raise vault.VaultError(code, "The trusted delivery encoding is invalid.") from error
    if len(decoded) != size or vault.b64(decoded) != value:
        raise vault.VaultError(code, "The trusted delivery encoding is invalid.")
    return decoded


def validate_model_request(value: Any) -> dict[str, Any]:
    """Validate the entire model-visible request and reject extra fields."""
    if not isinstance(value, dict) or set(value) != MODEL_REQUEST_KEYS:
        raise vault.VaultError(
            "MODEL_REQUEST_MALFORMED",
            "Vault requests may contain only action, resource, fields, and purpose.",
        )
    action = value.get("action")
    if action not in MODEL_ACTIONS:
        raise vault.VaultError("MODEL_ACTION_DENIED", "The requested Vault action is unsupported.")
    resource = vault.normalize_logical_id(value.get("resource"))
    if RESOURCE_PATTERN.fullmatch(resource) is None:
        raise vault.VaultError("MODEL_RESOURCE_INVALID", "The Vault logical resource identifier is invalid.")
    raw_fields = value.get("fields")
    if not isinstance(raw_fields, list) or len(raw_fields) > 32:
        raise vault.VaultError("FIELD_REQUIRED", "Vault requests require a bounded field-name list.")
    if action in {"deliver", "use"} and not raw_fields:
        raise vault.VaultError("FIELD_REQUIRED", "Private delivery requires an exact field selection.")
    if not all(isinstance(field, str) and FIELD_PATTERN.fullmatch(field) for field in raw_fields):
        raise vault.VaultError("FIELD_INVALID", "Vault field names are invalid.")
    fields = sorted(set(raw_fields))
    if len(fields) != len(raw_fields):
        raise vault.VaultError("FIELD_INVALID", "Vault field selection contains duplicates.")
    purpose = value.get("purpose")
    if not isinstance(purpose, str) or PURPOSE_PATTERN.fullmatch(purpose) is None:
        raise vault.VaultError("PURPOSE_REQUIRED", "Vault requests require a structured purpose code.")
    return {"action": action, "resource": resource, "fields": fields, "purpose": purpose}


@dataclass(frozen=True)
class TrustedContext:
    """Harness-owned context. No model-visible schema accepts this object."""

    source_kind: str
    platform: str
    chat_type: str
    user_id: str
    chat_id: str
    thread_id: str
    session_id: str
    message_id: str
    agent_id: str

    def validated(self) -> "TrustedContext":
        for value in (
            self.source_kind,
            self.platform,
            self.chat_type,
            self.user_id,
            self.chat_id,
            self.session_id,
            self.message_id,
        ):
            _text(value, maximum=512)
        _text(self.thread_id, maximum=512, allow_empty=True)
        _uuid(self.agent_id, "AGENT_ID_INVALID")
        return self

    def stable_destination(self) -> dict[str, str]:
        return {
            "platform": self.platform,
            "chat_type": self.chat_type,
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "thread_id": self.thread_id,
        }

    def exact_destination(self, capability: Mapping[str, Any] | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            **self.stable_destination(),
            "source_kind": self.source_kind,
            "session_id": self.session_id,
            "message_id": self.message_id,
        }
        if capability is not None:
            result["capability"] = dict(capability)
        return result


@dataclass(frozen=True)
class HarnessAuthority:
    issuer_instance: str
    key_id: str
    signing_key: bytes
    digest_key: bytes

    @classmethod
    def generate(cls, issuer_instance: str | None = None) -> "HarnessAuthority":
        nacl = vault.crypto()
        return cls(
            issuer_instance=issuer_instance or str(uuid.uuid4()),
            key_id=str(uuid.uuid4()),
            signing_key=bytes(nacl.signing.SigningKey.generate()),
            digest_key=nacl.bindings.randombytes(32),
        ).validated()

    def validated(self) -> "HarnessAuthority":
        _uuid(self.issuer_instance, "HARNESS_ID_INVALID")
        _uuid(self.key_id, "HARNESS_KEY_ID_INVALID")
        if len(self.signing_key) != 32 or len(self.digest_key) != 32:
            raise vault.VaultError("HARNESS_KEY_INVALID", "The trusted harness key material is invalid.")
        return self

    @property
    def public_key(self) -> bytes:
        return bytes(vault.crypto().signing.SigningKey(self.signing_key).verify_key)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.public_key).hexdigest()

    def resource_digest(self, resource: str) -> str:
        return _digest(self.digest_key, "resource", vault.normalize_logical_id(resource))

    def fields_digest(self, fields: list[str]) -> str:
        return _digest(self.digest_key, "fields", sorted(fields))

    def owner_destination_digest(self, destination: Mapping[str, Any]) -> str:
        return _digest(self.digest_key, "owner-destination", dict(destination))

    def exact_destination_digest(
        self,
        context: TrustedContext,
        capability: Mapping[str, Any] | None = None,
    ) -> str:
        return _digest(self.digest_key, "exact-destination", context.exact_destination(capability))

    def approve_and_attest(
        self,
        request: Mapping[str, Any],
        context: TrustedContext,
        *,
        audience: str,
        delivery_policy: str,
        safe_label: str,
        capability: Mapping[str, Any] | None = None,
        approve: Callable[[dict[str, Any]], bool],
        approval_id: str | None = None,
        request_id: str | None = None,
        now: int | None = None,
        ttl_seconds: int = 45,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Capture exact approval, then sign one short-lived envelope."""
        selected = validate_model_request(dict(request))
        context = context.validated()
        _uuid(audience, "AUDIENCE_INVALID")
        if selected["action"] not in {"deliver", "use"}:
            raise vault.VaultError("DELIVERY_ACTION_REQUIRED", "Attestation is only available for delivery or direct use.")
        if delivery_policy not in DELIVERY_POLICIES:
            raise vault.VaultError("DELIVERY_POLICY_INVALID", "The selected delivery policy is invalid.")
        if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 1 <= ttl_seconds <= MAX_ATTESTATION_TTL:
            raise vault.VaultError("ATTESTATION_TTL_INVALID", "Attestation lifetime must be from 1 to 60 seconds.")
        issued_at = int(time.time()) if now is None else now
        expires_at = issued_at + ttl_seconds
        request_id = _uuid(request_id, "ATTESTATION_MALFORMED") if request_id is not None else str(uuid.uuid4())
        approval_id = _uuid(approval_id, "APPROVAL_INVALID") if approval_id is not None else str(uuid.uuid4())
        destination_display = (
            f"{context.platform} direct message for the paired owner"
            if context.chat_type == "dm"
            else "this owner-local secure interface"
            if context.source_kind == "local_user"
            else "a restricted direct-use adapter"
        )
        prompt = {
            "schema": "megabrain.vault-approval-prompt.v1",
            "approval_id": approval_id,
            "request_id": request_id,
            "safe_label": _text(safe_label, maximum=160) if safe_label else "[protected resource]",
            "fields": selected["fields"],
            "purpose": selected["purpose"],
            "requester": context.agent_id,
            "destination": destination_display,
            "warning": "Approve only this exact one-time request. The selected fields will leave Vault for the named destination or direct-use adapter.",
            "expires_at": expires_at,
        }
        if approve(prompt) is not True:
            raise vault.VaultError("APPROVAL_DENIED", "The owner denied the exact private-delivery request.")
        capability_id = ""
        if capability is not None:
            capability_id = _text(capability.get("capability_id"), maximum=64)
        unsigned = {
            "schema": ATTESTATION_SCHEMA,
            "issuer_instance": self.issuer_instance,
            "key_id": self.key_id,
            "audience": audience,
            "request_id": request_id,
            "nonce": vault.b64(vault.crypto().bindings.randombytes(24)),
            "issued_at": issued_at,
            "expires_at": expires_at,
            "agent_id": context.agent_id,
            "session_id": context.session_id,
            "message_id": context.message_id,
            "source_kind": context.source_kind,
            "platform": context.platform,
            "chat_type": context.chat_type,
            "user_id": context.user_id,
            "chat_id": context.chat_id,
            "thread_id": context.thread_id,
            "action": selected["action"],
            "resource_digest": self.resource_digest(selected["resource"]),
            "fields_digest": self.fields_digest(selected["fields"]),
            "purpose": selected["purpose"],
            "approval_id": approval_id,
            "delivery_policy": delivery_policy,
            "capability_id": capability_id,
            "destination_binding": self.exact_destination_digest(context, capability),
        }
        signature = vault.crypto().signing.SigningKey(self.signing_key).sign(vault.canonical(unsigned)).signature
        return {**unsigned, "signature": vault.b64(signature)}, prompt


def _key_aad(vault_id: str, issuer_instance: str, key_id: str) -> bytes:
    return f"megabrain.vault-harness-digest.v1|{vault_id}|{issuer_instance}|{key_id}".encode()


def _header_identity(store: vault.VaultStore) -> tuple[str, str]:
    with store.connect() as connection:
        header = store.header(connection)
        return str(header["vault_id"]), str(header["brain_id"])


def _normalized_destinations(
    authority: HarnessAuthority,
    destinations: list[Mapping[str, Any]],
) -> list[tuple[bytes, str, str]]:
    if not destinations:
        raise vault.VaultError("DESTINATION_REQUIRED", "Harness pairing requires an exact owner destination.")
    normalized: list[tuple[bytes, str, str]] = []
    expected = {"platform", "chat_type", "user_id", "chat_id", "thread_id", "kind"}
    for destination in destinations:
        if not isinstance(destination, Mapping) or set(destination) != expected:
            raise vault.VaultError("DESTINATION_INVALID", "A paired destination is invalid.")
        stable = {
            key: _text(destination[key], maximum=512, allow_empty=key == "thread_id")
            for key in expected - {"kind"}
        }
        kind = _text(destination["kind"], maximum=32)
        if kind not in {"private_dm", "local_secure_ui"}:
            raise vault.VaultError("DESTINATION_INVALID", "A paired destination kind is invalid.")
        if kind == "private_dm" and stable["chat_type"] != "dm":
            raise vault.VaultError("DESTINATION_INVALID", "A private destination must be an exact direct message.")
        if kind == "local_secure_ui" and not (
            stable["platform"] == "local" and stable["chat_type"] == "local"
        ):
            raise vault.VaultError("DESTINATION_INVALID", "A local destination must be the local secure interface.")
        digest = vault.unb64(authority.owner_destination_digest(stable))
        normalized.append((digest, stable["platform"], kind))
    if len({row[0] for row in normalized}) != len(normalized):
        raise vault.VaultError("DESTINATION_INVALID", "Harness pairing contains duplicate destinations.")
    return normalized


def pair_harness(
    store: vault.VaultStore,
    master_key: bytes,
    authority: HarnessAuthority,
    destinations: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Owner-local pairing. Digest and signing keys never enter model JSON."""
    authority = authority.validated()
    vault_id, brain_id = _header_identity(store)
    encrypted_key, nonce = vault.encrypt(
        master_key,
        authority.digest_key,
        _key_aad(vault_id, authority.issuer_instance, authority.key_id),
    )
    normalized = _normalized_destinations(authority, destinations)
    with store.connect() as connection:
        if connection.execute(
            "SELECT 1 FROM harness_keys WHERE issuer_instance=? AND status='active'",
            (authority.issuer_instance,),
        ).fetchone():
            raise vault.VaultError("HARNESS_ALREADY_PAIRED", "The harness instance already has an active key.")
        connection.execute(
            "INSERT INTO harness_keys VALUES (?, ?, ?, ?, ?, ?, 'active', ?, NULL, NULL)",
            (
                authority.issuer_instance,
                authority.key_id,
                authority.public_key,
                encrypted_key,
                nonce,
                brain_id,
                vault.utc_now(),
            ),
        )
        for digest, platform, kind in normalized:
            connection.execute(
                "INSERT INTO harness_destinations VALUES (?, ?, ?, ?, ?, 'active', ?, NULL)",
                (authority.issuer_instance, authority.key_id, digest, platform, kind, vault.utc_now()),
            )
        store.audit(connection, None, "pair-harness", None, "allowed", "OWNER_LOCAL_CONTROL_PLANE", None)
    return {
        "ok": True,
        "issuer_instance": authority.issuer_instance,
        "key_id": authority.key_id,
        "fingerprint": authority.fingerprint,
        "destinations": len(normalized),
    }


def rotate_harness_key(
    store: vault.VaultStore,
    master_key: bytes,
    old_key_id: str,
    authority: HarnessAuthority,
    destinations: list[Mapping[str, Any]],
    *,
    grace_seconds: int = 300,
    now: int | None = None,
) -> dict[str, Any]:
    authority = authority.validated()
    _uuid(old_key_id, "HARNESS_KEY_ID_INVALID")
    if not isinstance(grace_seconds, int) or isinstance(grace_seconds, bool) or not 0 <= grace_seconds <= 3600:
        raise vault.VaultError("GRACE_PERIOD_INVALID", "Harness key grace must be from 0 to 3600 seconds.")
    current = int(time.time()) if now is None else now
    vault_id, brain_id = _header_identity(store)
    encrypted_key, nonce = vault.encrypt(
        master_key,
        authority.digest_key,
        _key_aad(vault_id, authority.issuer_instance, authority.key_id),
    )
    rows = _normalized_destinations(authority, destinations)
    with store.connect() as connection:
        old = connection.execute(
            "SELECT status FROM harness_keys WHERE issuer_instance=? AND key_id=?",
            (authority.issuer_instance, old_key_id),
        ).fetchone()
        if old is None or old["status"] != "active":
            raise vault.VaultError("HARNESS_KEY_NOT_ACTIVE", "The previous harness key is not active.")
        connection.execute(
            "INSERT INTO harness_keys VALUES (?, ?, ?, ?, ?, ?, 'active', ?, NULL, NULL)",
            (
                authority.issuer_instance,
                authority.key_id,
                authority.public_key,
                encrypted_key,
                nonce,
                brain_id,
                vault.utc_now(),
            ),
        )
        for digest, platform, kind in rows:
            connection.execute(
                "INSERT INTO harness_destinations VALUES (?, ?, ?, ?, ?, 'active', ?, NULL)",
                (authority.issuer_instance, authority.key_id, digest, platform, kind, vault.utc_now()),
            )
        connection.execute(
            "UPDATE harness_keys SET status='grace',grace_until=? WHERE issuer_instance=? AND key_id=?",
            (current + grace_seconds, authority.issuer_instance, old_key_id),
        )
        store.audit(connection, None, "rotate-harness", None, "allowed", "OWNER_LOCAL_CONTROL_PLANE", None)
    return {
        "ok": True,
        "issuer_instance": authority.issuer_instance,
        "key_id": authority.key_id,
        "fingerprint": authority.fingerprint,
        "destinations": len(rows),
        "previous_key_id": old_key_id,
        "grace_until": current + grace_seconds,
    }


def rollback_harness_key(
    store: vault.VaultStore,
    issuer_instance: str,
    restore_key_id: str,
    revoke_key_id: str,
    *,
    now: int | None = None,
) -> dict[str, Any]:
    current = int(time.time()) if now is None else now
    with store.connect() as connection:
        prior = connection.execute(
            "SELECT status,grace_until FROM harness_keys WHERE issuer_instance=? AND key_id=?",
            (issuer_instance, restore_key_id),
        ).fetchone()
        replacement = connection.execute(
            "SELECT status FROM harness_keys WHERE issuer_instance=? AND key_id=?",
            (issuer_instance, revoke_key_id),
        ).fetchone()
        if (
            prior is None
            or prior["status"] != "grace"
            or int(prior["grace_until"] or 0) < current
            or replacement is None
            or replacement["status"] != "active"
        ):
            raise vault.VaultError("HARNESS_ROLLBACK_DENIED", "Harness rollback is outside the grace window.")
        connection.execute(
            "UPDATE harness_keys SET status='active',grace_until=NULL WHERE issuer_instance=? AND key_id=?",
            (issuer_instance, restore_key_id),
        )
        connection.execute(
            "UPDATE harness_keys SET status='revoked',revoked_at=? WHERE issuer_instance=? AND key_id=?",
            (vault.utc_now(), issuer_instance, revoke_key_id),
        )
        connection.execute(
            "UPDATE harness_destinations SET status='revoked',revoked_at=? WHERE issuer_instance=? AND key_id=?",
            (vault.utc_now(), issuer_instance, revoke_key_id),
        )
        store.audit(connection, None, "rollback-harness", None, "allowed", "OWNER_LOCAL_CONTROL_PLANE", None)
    return {"ok": True, "restored_key_id": restore_key_id, "revoked_key_id": revoke_key_id}


def revoke_harness_key(store: vault.VaultStore, issuer_instance: str, key_id: str) -> dict[str, Any]:
    with store.connect() as connection:
        changed = connection.execute(
            "UPDATE harness_keys SET status='revoked',revoked_at=? WHERE issuer_instance=? AND key_id=? AND status!='revoked'",
            (vault.utc_now(), issuer_instance, key_id),
        ).rowcount
        connection.execute(
            "UPDATE harness_destinations SET status='revoked',revoked_at=? WHERE issuer_instance=? AND key_id=?",
            (vault.utc_now(), issuer_instance, key_id),
        )
        store.audit(connection, None, "revoke-harness", None, "allowed", "OWNER_LOCAL_CONTROL_PLANE", None)
    if not changed:
        raise vault.VaultError("HARNESS_KEY_NOT_FOUND", "The harness key was not found or is already revoked.")
    return {"ok": True, "revoked": True, "issuer_instance": issuer_instance, "key_id": key_id}


def default_delivery_policy(resource: str) -> str:
    category = vault.resource_class(vault.normalize_logical_id(resource))
    if category == "credentials":
        return "direct_use_only"
    if category in {"identity", "health", "finance", "recovery"}:
        return "local_secure_ui"
    return "never_reveal"


def set_resource_policy(
    store: vault.VaultStore,
    master_key: bytes,
    resource: str,
    policy: str,
) -> dict[str, Any]:
    resource = vault.normalize_logical_id(resource)
    if policy not in DELIVERY_POLICIES:
        raise vault.VaultError("DELIVERY_POLICY_INVALID", "The selected delivery policy is invalid.")
    category = vault.resource_class(resource)
    if category == "credentials" and policy not in {"direct_use_only", "never_reveal"}:
        raise vault.VaultError("CREDENTIAL_REVEAL_DENIED", "Credentials may be direct-use-only or never-reveal.")
    if category == "recovery" and policy not in {"local_secure_ui", "never_reveal"}:
        raise vault.VaultError("RECOVERY_DELIVERY_DENIED", "Recovery material is confined to the owner-local interface.")
    digest = store.resource_digest(master_key, resource)
    with store.connect() as connection:
        store._row_for(connection, master_key, resource)
        connection.execute(
            """INSERT INTO resource_delivery_policies VALUES (?, ?, ?)
            ON CONFLICT(resource_digest) DO UPDATE SET policy=excluded.policy,updated_at=excluded.updated_at""",
            (digest, policy, vault.utc_now()),
        )
        store.audit(connection, None, "set-delivery-policy", digest, "allowed", "OWNER_LOCAL_CONTROL_PLANE", None)
    return {
        "ok": True,
        "policy": policy,
        "warning": "Private DM delivery leaves the owner-local device boundary." if policy == "private_dm_opt_in" else None,
    }


def register_direct_use_capability(
    store: vault.VaultStore,
    master_key: bytes,
    resource: str,
    *,
    capability_id: str,
    adapter_id: str,
    host: str,
    operation: str,
    fields: list[str],
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    resource = vault.normalize_logical_id(resource)
    if vault.resource_class(resource) != "credentials":
        raise vault.VaultError("DIRECT_USE_RESOURCE_DENIED", "Direct-use capabilities require a credential resource.")
    for value in (capability_id, adapter_id, operation):
        if PURPOSE_PATTERN.fullmatch(value or "") is None:
            raise vault.VaultError("CAPABILITY_INVALID", "The direct-use capability is invalid.")
    if not isinstance(host, str) or HOST_PATTERN.fullmatch(host) is None:
        raise vault.VaultError("CAPABILITY_HOST_INVALID", "The direct-use host policy is invalid.")
    if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool) or not 1 <= timeout_seconds <= 30:
        raise vault.VaultError("CAPABILITY_TIMEOUT_INVALID", "Direct-use timeout must be from 1 to 30 seconds.")
    if not fields or len(fields) > 16 or not all(isinstance(field, str) and FIELD_PATTERN.fullmatch(field) for field in fields):
        raise vault.VaultError("CAPABILITY_FIELDS_INVALID", "Direct-use fields are invalid.")
    selected = sorted(set(fields))
    if len(selected) != len(fields):
        raise vault.VaultError("CAPABILITY_FIELDS_INVALID", "Direct-use fields contain duplicates.")
    with store.connect() as connection:
        row = store._row_for(connection, master_key, resource)
        payload = store._payload(master_key, row)
        available = set(payload.get("fields", {}))
        payload.get("fields", {}).clear()
        payload.clear()
        if not set(selected) <= available:
            raise vault.VaultError("CAPABILITY_FIELDS_INVALID", "A direct-use field does not exist.")
        digest = store.resource_digest(master_key, resource)
        connection.execute(
            """INSERT INTO direct_use_capabilities VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, NULL)
            ON CONFLICT(resource_digest,capability_id) DO UPDATE SET
            adapter_id=excluded.adapter_id,host=excluded.host,operation=excluded.operation,
            fields_json=excluded.fields_json,timeout_seconds=excluded.timeout_seconds,
            status='active',created_at=excluded.created_at,revoked_at=NULL""",
            (
                digest,
                capability_id,
                adapter_id,
                host,
                operation,
                json.dumps(selected, separators=(",", ":")),
                timeout_seconds,
                vault.utc_now(),
            ),
        )
        store.audit(connection, None, "grant-direct-use", digest, "allowed", "OWNER_LOCAL_CONTROL_PLANE", None)
    return {
        "ok": True,
        "capability_id": capability_id,
        "adapter_id": adapter_id,
        "host": host,
        "operation": operation,
        "fields": selected,
        "timeout_seconds": timeout_seconds,
    }


def revoke_direct_use_capability(
    store: vault.VaultStore,
    master_key: bytes,
    resource: str,
    capability_id: str,
) -> dict[str, Any]:
    digest = store.resource_digest(master_key, vault.normalize_logical_id(resource))
    with store.connect() as connection:
        changed = connection.execute(
            """UPDATE direct_use_capabilities SET status='revoked',revoked_at=?
            WHERE resource_digest=? AND capability_id=? AND status='active'""",
            (vault.utc_now(), digest, capability_id),
        ).rowcount
        store.audit(connection, None, "revoke-direct-use", digest, "allowed", "OWNER_LOCAL_CONTROL_PLANE", None)
    if not changed:
        raise vault.VaultError("CAPABILITY_NOT_FOUND", "The direct-use capability was not found.")
    return {"ok": True, "revoked": True, "capability_id": capability_id}


def _delivery_policy(connection: Any, store: vault.VaultStore, master_key: bytes, resource: str) -> str:
    digest = store.resource_digest(master_key, resource)
    row = connection.execute(
        "SELECT policy FROM resource_delivery_policies WHERE resource_digest=?",
        (digest,),
    ).fetchone()
    return str(row["policy"]) if row is not None else default_delivery_policy(resource)


def _audit_delivery(
    store: vault.VaultStore,
    *,
    envelope: Mapping[str, Any] | None,
    outcome: str,
    reason: str,
    resource_digest: bytes | None = None,
    fields_digest: bytes | None = None,
    destination_digest: bytes | None = None,
) -> bool:
    data = envelope or {}
    try:
        with store.connect() as connection:
            connection.execute(
                "INSERT INTO delivery_audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    vault.utc_now(),
                    data.get("issuer_instance") if isinstance(data.get("issuer_instance"), str) else None,
                    data.get("key_id") if isinstance(data.get("key_id"), str) else None,
                    data.get("agent_id") if isinstance(data.get("agent_id"), str) else None,
                    data.get("action") if isinstance(data.get("action"), str) else "unknown",
                    data.get("delivery_policy") if isinstance(data.get("delivery_policy"), str) else None,
                    resource_digest,
                    fields_digest,
                    destination_digest,
                    outcome,
                    reason,
                    data.get("request_id") if isinstance(data.get("request_id"), str) else None,
                    data.get("approval_id") if isinstance(data.get("approval_id"), str) else None,
                ),
            )
        return True
    except Exception:
        return False


def _decode_digest(value: Any) -> bytes:
    return _unb64_exact(value, 32, "ATTESTATION_MALFORMED")


def _capability_descriptor(row: Any) -> dict[str, Any]:
    return {
        "capability_id": str(row["capability_id"]),
        "adapter_id": str(row["adapter_id"]),
        "host": str(row["host"]),
        "operation": str(row["operation"]),
        "fields": json.loads(row["fields_json"]),
        "timeout_seconds": int(row["timeout_seconds"]),
    }


def authorize_and_seal_release(
    store: vault.VaultStore,
    master_key: bytes,
    request: Mapping[str, Any],
    envelope: Mapping[str, Any],
    *,
    now: int | None = None,
) -> dict[str, Any]:
    """Validate, consume, decrypt, and seal selected fields to the harness."""
    selected = validate_model_request(dict(request))
    current = int(time.time()) if now is None else now
    raw_envelope = dict(envelope) if isinstance(envelope, Mapping) else {}
    resource_digest: bytes | None = None
    fields_digest: bytes | None = None
    destination_digest: bytes | None = None
    try:
        if not isinstance(envelope, Mapping) or set(envelope) != ATTESTATION_KEYS:
            raise vault.VaultError("ATTESTATION_MALFORMED", "The trusted delivery envelope is malformed.")
        if envelope.get("schema") != ATTESTATION_SCHEMA:
            raise vault.VaultError("ATTESTATION_SCHEMA_UNSUPPORTED", "The trusted delivery schema is unsupported.")
        issuer = _uuid(envelope.get("issuer_instance"), "HARNESS_ID_INVALID")
        key_id = _uuid(envelope.get("key_id"), "HARNESS_KEY_ID_INVALID")
        request_id = _uuid(envelope.get("request_id"), "ATTESTATION_MALFORMED")
        approval_id = _uuid(envelope.get("approval_id"), "APPROVAL_INVALID")
        agent_id = _uuid(envelope.get("agent_id"), "AGENT_ID_INVALID")
        audience = _uuid(envelope.get("audience"), "AUDIENCE_INVALID")
        issued_at = envelope.get("issued_at")
        expires_at = envelope.get("expires_at")
        if (
            not isinstance(issued_at, int)
            or isinstance(issued_at, bool)
            or not isinstance(expires_at, int)
            or isinstance(expires_at, bool)
            or expires_at <= issued_at
            or expires_at - issued_at > MAX_ATTESTATION_TTL
            or issued_at > current + MAX_ATTESTATION_FUTURE_SKEW
            or expires_at < current
        ):
            raise vault.VaultError("ATTESTATION_EXPIRED", "The trusted delivery envelope is outside its short lifetime.")
        nonce = _text(envelope.get("nonce"), maximum=64)
        _unb64_exact(nonce, 24, "ATTESTATION_MALFORMED")
        signature = _text(envelope.get("signature"), maximum=128)
        signature_bytes = _unb64_exact(signature, 64, "ATTESTATION_SIGNATURE_INVALID")
        for key in (
            "session_id",
            "message_id",
            "source_kind",
            "platform",
            "chat_type",
            "user_id",
            "chat_id",
        ):
            _text(envelope.get(key), maximum=512)
        _text(envelope.get("thread_id"), maximum=512, allow_empty=True)
        if envelope.get("action") != selected["action"] or selected["action"] not in {"deliver", "use"}:
            raise vault.VaultError("ATTESTATION_ACTION_MISMATCH", "The trusted delivery action does not match the request.")
        if envelope.get("purpose") != selected["purpose"]:
            raise vault.VaultError("ATTESTATION_PURPOSE_MISMATCH", "The trusted delivery purpose does not match the request.")
        policy = envelope.get("delivery_policy")
        if policy not in DELIVERY_POLICIES:
            raise vault.VaultError("DELIVERY_POLICY_INVALID", "The trusted delivery policy is invalid.")
        resource_digest = _decode_digest(envelope.get("resource_digest"))
        fields_digest = _decode_digest(envelope.get("fields_digest"))
        destination_digest = _decode_digest(envelope.get("destination_binding"))
        with store.connect() as connection:
            header = store.header(connection)
            if audience != header["brain_id"]:
                raise vault.VaultError("ATTESTATION_AUDIENCE_MISMATCH", "The trusted delivery audience is invalid.")
            key = connection.execute(
                "SELECT * FROM harness_keys WHERE issuer_instance=? AND key_id=?",
                (issuer, key_id),
            ).fetchone()
            if key is None:
                raise vault.VaultError("HARNESS_KEY_UNKNOWN", "The trusted harness key is not paired.")
            if key["status"] == "revoked":
                raise vault.VaultError("HARNESS_KEY_REVOKED", "The trusted harness key is revoked.")
            if key["status"] == "grace" and int(key["grace_until"] or 0) < current:
                raise vault.VaultError("HARNESS_KEY_EXPIRED", "The trusted harness key grace window expired.")
            if key["audience"] != audience:
                raise vault.VaultError("ATTESTATION_AUDIENCE_MISMATCH", "The trusted delivery audience is invalid.")
            unsigned = dict(envelope)
            unsigned.pop("signature", None)
            nacl = vault.crypto()
            try:
                nacl.signing.VerifyKey(bytes(key["public_key"])).verify(vault.canonical(unsigned), signature_bytes)
            except (nacl.exceptions.BadSignatureError, ValueError, vault.VaultError) as error:
                raise vault.VaultError("ATTESTATION_SIGNATURE_INVALID", "The trusted delivery signature is invalid.") from error
            digest_key = vault.decrypt(
                master_key,
                bytes(key["encrypted_digest_key"]),
                bytes(key["digest_key_nonce"]),
                _key_aad(str(header["vault_id"]), issuer, key_id),
            )
            expected_resource = _digest(digest_key, "resource", selected["resource"])
            expected_fields = _digest(digest_key, "fields", selected["fields"])
            if not hmac.compare_digest(envelope["resource_digest"], expected_resource):
                raise vault.VaultError("ATTESTATION_RESOURCE_MISMATCH", "The trusted resource binding does not match.")
            if not hmac.compare_digest(envelope["fields_digest"], expected_fields):
                raise vault.VaultError("ATTESTATION_FIELDS_MISMATCH", "The trusted field binding does not match.")
            context = TrustedContext(
                source_kind=envelope["source_kind"],
                platform=envelope["platform"],
                chat_type=envelope["chat_type"],
                user_id=envelope["user_id"],
                chat_id=envelope["chat_id"],
                thread_id=envelope["thread_id"],
                session_id=envelope["session_id"],
                message_id=envelope["message_id"],
                agent_id=agent_id,
            ).validated()
            resource_vault_digest = store.resource_digest(master_key, selected["resource"])
            configured_policy = _delivery_policy(connection, store, master_key, selected["resource"])
            if policy != configured_policy:
                raise vault.VaultError("DELIVERY_POLICY_MISMATCH", "The signed policy does not match the owner policy.")
            capability: dict[str, Any] | None = None
            capability_id = envelope.get("capability_id")
            if selected["action"] == "use":
                if policy != "direct_use_only" or not isinstance(capability_id, str) or not capability_id:
                    raise vault.VaultError("DIRECT_USE_POLICY_REQUIRED", "Direct use requires an active capability policy.")
                capability_row = connection.execute(
                    """SELECT * FROM direct_use_capabilities
                    WHERE resource_digest=? AND capability_id=? AND status='active'""",
                    (resource_vault_digest, capability_id),
                ).fetchone()
                if capability_row is None:
                    raise vault.VaultError("CAPABILITY_REVOKED", "The direct-use capability is missing or revoked.")
                capability = _capability_descriptor(capability_row)
                if selected["fields"] != capability["fields"]:
                    raise vault.VaultError("CAPABILITY_FIELDS_DENIED", "The request exceeds the direct-use field capability.")
            elif capability_id != "":
                raise vault.VaultError("CAPABILITY_UNEXPECTED", "Private delivery cannot include a direct-use capability.")
            expected_destination = _digest(digest_key, "exact-destination", context.exact_destination(capability))
            if not hmac.compare_digest(envelope["destination_binding"], expected_destination):
                raise vault.VaultError("DESTINATION_BINDING_MISMATCH", "The exact delivery destination does not match.")
            if (
                context.source_kind in DENIED_SOURCE_KINDS
                or context.source_kind not in {"gateway_user", "local_user"}
                or context.chat_type in DENIED_CHAT_TYPES
            ):
                raise vault.VaultError("DELIVERY_CONTEXT_DENIED", "This source or chat type cannot receive private delivery.")
            if context.platform == "email":
                raise vault.VaultError("DELIVERY_CONTEXT_DENIED", "Email cannot receive private delivery.")
            owner_destination = vault.unb64(_digest(digest_key, "owner-destination", context.stable_destination()))
            destination = connection.execute(
                """SELECT kind FROM harness_destinations WHERE issuer_instance=? AND key_id=?
                AND destination_digest=? AND status='active'""",
                (issuer, key_id, owner_destination),
            ).fetchone()
            if destination is None:
                raise vault.VaultError("DESTINATION_NOT_PAIRED", "The exact owner destination is not paired.")
            if policy == "private_dm_opt_in" and not (
                context.source_kind == "gateway_user" and context.chat_type == "dm" and destination["kind"] == "private_dm"
            ):
                raise vault.VaultError("PRIVATE_DM_REQUIRED", "This policy permits only the paired live owner DM.")
            if policy == "local_secure_ui" and not (
                context.source_kind == "local_user" and context.platform == "local" and destination["kind"] == "local_secure_ui"
            ):
                raise vault.VaultError("LOCAL_SECURE_UI_REQUIRED", "This policy permits only the owner-local secure interface.")
            if policy in {"metadata_only", "never_reveal"}:
                raise vault.VaultError("DELIVERY_POLICY_DENIED", "The owner policy forbids plaintext release.")
            if policy == "direct_use_only" and selected["action"] != "use":
                raise vault.VaultError("DIRECT_USE_ONLY", "This resource may be used only by a bounded adapter.")
            if policy == "direct_use_only" and not (
                (context.source_kind == "gateway_user" and context.chat_type == "dm" and destination["kind"] == "private_dm")
                or (
                    context.source_kind == "local_user"
                    and context.platform == "local"
                    and context.chat_type == "local"
                    and destination["kind"] == "local_secure_ui"
                )
            ):
                raise vault.VaultError(
                    "DIRECT_USE_CONTEXT_DENIED",
                    "Direct use requires the paired live owner DM or owner-local secure interface.",
                )
            grant = connection.execute("SELECT * FROM agent_grants WHERE agent_id=?", (agent_id,)).fetchone()
            if grant is None or grant["status"] != "active":
                raise vault.VaultError("AGENT_UNAUTHORIZED", "The requesting agent has no active Vault grant.")
            scopes = set(json.loads(grant["scopes_json"]))
            classes = set(json.loads(grant["resource_classes_json"]))
            category = vault.resource_class(selected["resource"])
            if selected["action"] == "deliver":
                required = {"vault.reveal", f"{category}.reveal"}
            else:
                required = {"credentials.use"}
            if not required <= scopes or (classes and category not in classes):
                raise vault.VaultError("SCOPE_DENIED", "The requesting agent lacks the exact delivery scope.")
            if connection.execute(
                "SELECT 1 FROM attested_requests WHERE request_id=? OR nonce=? OR approval_id=?",
                (request_id, nonce, approval_id),
            ).fetchone():
                raise vault.VaultError("ATTESTATION_REPLAYED", "The one-shot delivery approval was already consumed.")
            try:
                connection.execute(
                    "INSERT INTO attested_requests VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (request_id, nonce, approval_id, issuer, key_id, issued_at, expires_at, vault.utc_now()),
                )
            except sqlite3.IntegrityError as error:
                raise vault.VaultError(
                    "ATTESTATION_REPLAYED",
                    "The one-shot delivery approval was already consumed.",
                ) from error
        revealed = store.reveal(master_key, selected["resource"], selected["fields"])
        protected_fields = revealed["fields"]
        try:
            inner = {
                "schema": RELEASE_SCHEMA,
                "request_id": request_id,
                "approval_id": approval_id,
                "action": selected["action"],
                "destination_binding": envelope["destination_binding"],
                "capability": capability,
                "fields": protected_fields,
            }
            verify_key = vault.crypto().signing.VerifyKey(bytes(key["public_key"]))
            sealed = vault.crypto().public.SealedBox(verify_key.to_curve25519_public_key()).encrypt(vault.canonical(inner))
        finally:
            protected_fields.clear()
            revealed.clear()
        audited = _audit_delivery(
            store,
            envelope=envelope,
            outcome="allowed",
            reason="SEALED_TO_TRUSTED_ADAPTER",
            resource_digest=resource_digest,
            fields_digest=fields_digest,
            destination_digest=destination_digest,
        )
        if not audited:
            raise vault.VaultError("AUDIT_WRITE_FAILED", "The value-free private-delivery audit could not be recorded.")
        return {
            "ok": True,
            "request_id": request_id,
            "approval_id": approval_id,
            "sealed_release": vault.b64(sealed),
        }
    except vault.VaultError as error:
        _audit_delivery(
            store,
            envelope=raw_envelope,
            outcome="denied",
            reason=error.code,
            resource_digest=resource_digest,
            fields_digest=fields_digest,
            destination_digest=destination_digest,
        )
        raise


def request_attested_release(
    store: vault.VaultStore,
    request: Mapping[str, Any],
    envelope: Mapping[str, Any],
) -> dict[str, Any]:
    """Trusted harness client for the unlocked broker's opaque release method."""
    selected = validate_model_request(dict(request))
    if not isinstance(envelope, Mapping):
        raise vault.VaultError("ATTESTATION_MALFORMED", "The trusted delivery envelope is malformed.")
    return vault.broker_socket_request(
        vault.broker_socket_path(store.paths.runtime),
        {
            "method": "attested.release",
            "request": selected,
            "attestation": dict(envelope),
        },
    )


class TrustedAdapter(Protocol):
    adapter_id: str
    host: str
    operation: str

    def deliver(self, fields: Mapping[str, Any], *, timeout_seconds: int | None = None) -> Mapping[str, Any]: ...


def _contains_secret(value: Any, secrets: list[str]) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_secret(key, secrets) or _contains_secret(item, secrets) for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return any(_contains_secret(item, secrets) for item in value)
    text = str(value)
    return any(secret and secret in text for secret in secrets)


def _secret_strings(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        result: list[str] = []
        for item in value.values():
            result.extend(_secret_strings(item))
        return result
    if isinstance(value, (list, tuple, set)):
        result = []
        for item in value:
            result.extend(_secret_strings(item))
        return result
    return [str(value)]


def open_and_deliver(
    authority: HarnessAuthority,
    sealed_response: Mapping[str, Any],
    envelope: Mapping[str, Any],
    adapter: TrustedAdapter,
) -> dict[str, Any]:
    """Trusted-adapter boundary. Returns a receipt that cannot contain values."""
    authority = authority.validated()
    if not isinstance(sealed_response, Mapping) or set(sealed_response) != {
        "ok",
        "request_id",
        "approval_id",
        "sealed_release",
    }:
        raise vault.VaultError("SEALED_RELEASE_INVALID", "The opaque Vault release is invalid.")
    if sealed_response.get("ok") is not True:
        raise vault.VaultError("SEALED_RELEASE_INVALID", "The opaque Vault release is invalid.")
    if envelope.get("issuer_instance") != authority.issuer_instance or envelope.get("key_id") != authority.key_id:
        raise vault.VaultError("SEALED_RELEASE_MISMATCH", "The opaque Vault release belongs to another harness key.")
    nacl = vault.crypto()
    try:
        signature = _unb64_exact(envelope.get("signature"), 64, "ATTESTATION_SIGNATURE_INVALID")
        unsigned = dict(envelope)
        unsigned.pop("signature", None)
        nacl.signing.VerifyKey(authority.public_key).verify(vault.canonical(unsigned), signature)
    except (vault.VaultError, nacl.exceptions.BadSignatureError, ValueError) as error:
        raise vault.VaultError("ATTESTATION_SIGNATURE_INVALID", "The trusted delivery signature is invalid.") from error
    if sealed_response.get("request_id") != envelope.get("request_id") or sealed_response.get("approval_id") != envelope.get("approval_id"):
        raise vault.VaultError("SEALED_RELEASE_MISMATCH", "The opaque Vault release does not match its approval.")
    try:
        sealed_value = sealed_response.get("sealed_release")
        if not isinstance(sealed_value, str) or ENCODED_PATTERN.fullmatch(sealed_value) is None:
            raise ValueError("invalid sealed release encoding")
        sealed = vault.unb64(sealed_value)
        if not sealed or vault.b64(sealed) != sealed_value:
            raise ValueError("invalid sealed release encoding")
        signing_key = vault.crypto().signing.SigningKey(authority.signing_key)
        plaintext = vault.crypto().public.SealedBox(signing_key.to_curve25519_private_key()).decrypt(sealed)
        release = json.loads(plaintext)
    except Exception as error:
        raise vault.VaultError("SEALED_RELEASE_INVALID", "The opaque Vault release could not be opened.") from error
    if (
        not isinstance(release, dict)
        or release.get("schema") != RELEASE_SCHEMA
        or release.get("request_id") != envelope.get("request_id")
        or release.get("approval_id") != envelope.get("approval_id")
        or release.get("destination_binding") != envelope.get("destination_binding")
        or release.get("action") != envelope.get("action")
        or not isinstance(release.get("fields"), dict)
    ):
        raise vault.VaultError("SEALED_RELEASE_MISMATCH", "The opaque Vault release does not match its attestation.")
    fields: MutableMapping[str, Any] = release["fields"]
    secrets = _secret_strings(fields)
    capability = release.get("capability")
    timeout_seconds = int(capability["timeout_seconds"]) if isinstance(capability, dict) else None
    try:
        if isinstance(capability, dict) and (
            getattr(adapter, "adapter_id", None) != capability.get("adapter_id")
            or getattr(adapter, "host", None) != capability.get("host")
            or getattr(adapter, "operation", None) != capability.get("operation")
        ):
            raise vault.VaultError("ADAPTER_CAPABILITY_MISMATCH", "The trusted adapter does not match the capability.")
        receipt = adapter.deliver(fields, timeout_seconds=timeout_seconds)
        if not isinstance(receipt, Mapping) or _contains_secret(receipt, secrets):
            raise vault.VaultError("ADAPTER_OUTPUT_SECRET", "The trusted adapter returned protected material.")
        return {
            "ok": True,
            "delivered": True,
            "action": release["action"],
            "receipt": dict(receipt),
        }
    finally:
        fields.clear()
        release.clear()


class SyntheticTokenCheckAdapter:
    """Narrow no-network direct-use adapter for synthetic tests and demos only."""

    adapter_id = "synthetic.token-check"
    host = "api.example.invalid"
    operation = "token-check"

    def deliver(self, fields: Mapping[str, Any], *, timeout_seconds: int | None = None) -> Mapping[str, Any]:
        if timeout_seconds is None or not 1 <= timeout_seconds <= 30:
            raise vault.VaultError("ADAPTER_TIMEOUT_INVALID", "The direct-use timeout policy is invalid.")
        token = fields.get("password")
        if not isinstance(token, str) or not token:
            raise vault.VaultError("ADAPTER_INPUT_INVALID", "The synthetic token input is invalid.")
        return {
            "provider": "synthetic",
            "host": self.host,
            "operation": self.operation,
            "authenticated": True,
        }


def delivery_audit_list(store: vault.VaultStore, limit: int = 100) -> dict[str, Any]:
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise vault.VaultError("INVALID_LIMIT", "Delivery audit limit must be an integer.")
    with store.connect() as connection:
        rows = connection.execute(
            """SELECT event_id,timestamp,issuer_instance,key_id,agent_id,action,delivery_policy,
            outcome,reason_code,request_id,approval_id FROM delivery_audit_events
            ORDER BY rowid DESC LIMIT ?""",
            (max(1, min(limit, 500)),),
        ).fetchall()
    return {"ok": True, "events": [dict(row) for row in rows]}
