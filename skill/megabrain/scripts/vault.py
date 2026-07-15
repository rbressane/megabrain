#!/usr/bin/env python3
"""Built-in encrypted MegaBrain Vault.

The module intentionally keeps the optional PyNaCl import behind vault operations so
ordinary Markdown-brain reads remain dependency-free.
"""

from __future__ import annotations

import base64
import contextlib
import fcntl
import hashlib
import hmac
import importlib
import json
import os
import re
import shutil
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Iterable


VAULT_SCHEMA_VERSION = 1
VAULT_SUITE = "pynacl-argon2id-xchacha20poly1305-ed25519-v1"
ITEM_SCHEMA = "megabrain.vault-item.v1"
BACKUP_SCHEMA = "megabrain.vault-backup.v1"
AGENT_KEY_SCHEMA = "megabrain.vault-agent-key.v1"
REQUEST_SCHEMA = "megabrain.vault-request.v1"
ATTACHMENT_MAGIC = b"MBVAT1\n"
ATTACHMENT_CHUNK_SIZE = 1024 * 1024
MAX_ATTACHMENT_SIZE = 100 * 1024 * 1024
MAX_BACKUP_FILES = 10_002
MAX_BACKUP_MANIFEST_SIZE = 1024 * 1024
MAX_BACKUP_DATABASE_SIZE = 4 * 1024 * 1024 * 1024
MAX_BACKUP_EXPANDED_SIZE = 16 * 1024 * 1024 * 1024
MAX_CLOCK_SKEW_SECONDS = 60
RECOVERY_PREFIX = "MBRK1-"
GLOBAL_SCOPES = {
    "vault.metadata",
    "vault.locate",
    "vault.reveal",
    "vault.write",
    "vault.attach",
    "vault.delete",
    "vault.admin",
}
RESOURCE_SCOPES = {
    "identity.metadata",
    "identity.reveal",
    "credentials.use",
    "credentials.reveal",
    "health.metadata",
    "health.reveal",
    "finance.metadata",
    "finance.reveal",
}
ITEM_TYPE_FIELDS = {
    "passport": {
        "document_number", "holder_name", "nationality", "date_of_birth",
        "issuing_authority", "issued_on", "expires_on",
    },
    "identity": {
        "id_number", "legal_name", "date_of_birth", "issuing_authority",
        "issued_on", "expires_on",
    },
    "identity-document": {
        "document_number", "id_number", "document_kind", "holder_name", "legal_name",
        "nationality", "date_of_birth", "issuing_authority", "issued_on", "expires_on",
    },
    "credential": {
        "service", "username", "password", "url", "totp_seed", "recovery_codes", "notes",
    },
    "recovery-code": {"service", "codes", "notes"},
    "health-record": {
        "record_kind", "provider", "patient_name", "recorded_on", "value", "unit", "notes",
    },
    "financial-account": {
        "institution", "holder_name", "account_number", "routing_number", "iban", "swift", "notes",
    },
}
ACTION_SCOPES = {
    "metadata": "vault.metadata",
    "locate": "vault.locate",
    "reveal": "vault.reveal",
    "put": "vault.write",
    "attach": "vault.attach",
    "delete": "vault.delete",
    "admin": "vault.admin",
}


class VaultError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> bool:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def crypto() -> Any:
    try:
        import nacl
        import nacl.bindings
        import nacl.exceptions
        import nacl.pwhash
        import nacl.signing
    except ImportError as error:
        raise VaultError(
            "VAULT_DEPENDENCY_MISSING",
            "MegaBrain Vault requires PyNaCl 1.5 or newer; install requirements-vault.txt.",
        ) from error
    try:
        version = tuple(int(part) for part in nacl.__version__.split(".")[:2])
    except (AttributeError, ValueError):
        version = (0, 0)
    if version < (1, 5) or version >= (2, 0):
        raise VaultError(
            "VAULT_DEPENDENCY_INCOMPATIBLE",
            "MegaBrain Vault requires PyNaCl 1.5 or newer and below 2.0; install requirements-vault.txt.",
        )
    return nacl


def dependency_path(home: Path) -> Path:
    return home / ".megabrain" / "runtime" / "vault-deps" / f"python-{sys.version_info.major}.{sys.version_info.minor}"


def configure_dependency(home: Path) -> None:
    target = dependency_path(home)
    if target.exists() and str(target) not in sys.path:
        sys.path.insert(0, str(target))
        importlib.invalidate_caches()


def ensure_dependency(home: Path) -> None:
    configure_dependency(home)
    try:
        crypto()
        return
    except VaultError as error:
        if error.code != "VAULT_DEPENDENCY_MISSING":
            raise
    target = dependency_path(home)
    secure_directory(target)
    installed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--no-cache-dir",
            "--target",
            str(target),
            "PyNaCl>=1.5.0,<2.0.0",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if installed.returncode != 0:
        shutil.rmtree(target, ignore_errors=True)
        raise VaultError(
            "VAULT_DEPENDENCY_INSTALL_FAILED",
            "PyNaCl could not be installed; the Vault was not activated.",
            {"returncode": installed.returncode},
        )
    configure_dependency(home)
    crypto()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def unb64(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as error:
        raise VaultError("INVALID_RECOVERY_KEY", "Recovery material is invalid.") from error


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def normalize_logical_id(value: str) -> str:
    if not isinstance(value, str) or "://" not in value or len(value) > 512:
        raise VaultError("INVALID_RESOURCE", "A versioned logical resource identifier is required.")
    scheme, path = value.strip().split("://", 1)
    normalized = f"{scheme.lower()}://{'/'.join(part for part in path.strip('/').split('/') if part)}"
    if not scheme or not path or len(normalized) > 512:
        raise VaultError("INVALID_RESOURCE", "A versioned logical resource identifier is required.")
    return normalized


def resource_class(logical_id: str) -> str:
    scheme = logical_id.split("://", 1)[0].lower()
    return {
        "identity": "identity",
        "credentials": "credentials",
        "credential": "credentials",
        "health": "health",
        "finance": "finance",
    }.get(scheme, scheme)


def safe_permissions(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError as error:
        raise VaultError("UNSAFE_PERMISSIONS", "Vault permissions could not be secured.") from error


def secure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    safe_permissions(path, 0o700)


def secure_json(path: Path, value: dict[str, Any]) -> None:
    secure_directory(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=True, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        safe_permissions(path, 0o600)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def derive_passphrase_key(passphrase: str, salt: bytes, opslimit: int, memlimit: int) -> bytes:
    if not isinstance(passphrase, str) or len(passphrase) < 12:
        raise VaultError("WEAK_PASSPHRASE", "Vault passphrases must contain at least 12 characters.")
    nacl = crypto()
    if (
        not isinstance(salt, bytes)
        or len(salt) != nacl.pwhash.argon2id.SALTBYTES
        or opslimit != int(nacl.pwhash.argon2id.OPSLIMIT_INTERACTIVE)
        or memlimit != int(nacl.pwhash.argon2id.MEMLIMIT_INTERACTIVE)
    ):
        raise VaultError("VAULT_HEADER_INVALID", "Vault key-derivation parameters are invalid.")
    try:
        return nacl.pwhash.argon2id.kdf(
            32,
            passphrase.encode("utf-8"),
            salt,
            opslimit=opslimit,
            memlimit=memlimit,
        )
    except (ValueError, MemoryError) as error:
        raise VaultError("VAULT_HEADER_INVALID", "Vault key-derivation parameters are invalid.") from error


def encrypt(key: bytes, plaintext: bytes, aad: bytes) -> tuple[bytes, bytes]:
    nacl = crypto()
    nonce = nacl.bindings.randombytes(nacl.bindings.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES)
    ciphertext = nacl.bindings.crypto_aead_xchacha20poly1305_ietf_encrypt(plaintext, aad, nonce, key)
    return ciphertext, nonce


def decrypt(key: bytes, ciphertext: bytes, nonce: bytes, aad: bytes) -> bytes:
    nacl = crypto()
    if (
        not isinstance(key, bytes)
        or len(key) != nacl.bindings.crypto_aead_xchacha20poly1305_ietf_KEYBYTES
        or not isinstance(nonce, bytes)
        or len(nonce) != nacl.bindings.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES
        or not isinstance(ciphertext, bytes)
        or len(ciphertext) < nacl.bindings.crypto_aead_xchacha20poly1305_ietf_ABYTES
    ):
        raise VaultError("AUTHENTICATION_FAILED", "Vault authentication failed.")
    try:
        return nacl.bindings.crypto_aead_xchacha20poly1305_ietf_decrypt(ciphertext, aad, nonce, key)
    except (nacl.exceptions.CryptoError, TypeError, ValueError) as error:
        raise VaultError("AUTHENTICATION_FAILED", "Vault authentication failed.") from error


def recovery_bytes(value: str) -> bytes:
    if not isinstance(value, str) or not value.startswith(RECOVERY_PREFIX):
        raise VaultError("INVALID_RECOVERY_KEY", "Recovery material is invalid.")
    raw = unb64(value[len(RECOVERY_PREFIX):])
    if len(raw) != 32:
        raise VaultError("INVALID_RECOVERY_KEY", "Recovery material is invalid.")
    return raw


@dataclass(frozen=True)
class VaultPaths:
    root: Path
    database: Path
    attachments: Path
    runtime: Path
    audit: Path


class SensitiveStore:
    """Provider seam for future external sensitive stores."""

    def put(self, master_key: bytes, item: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def metadata(self, master_key: bytes, logical_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def reveal(self, master_key: bytes, logical_id: str, fields: Iterable[str]) -> dict[str, Any]:
        raise NotImplementedError

    def delete(self, master_key: bytes, logical_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def attach(self, master_key: bytes, logical_id: str, source: Path) -> dict[str, Any]:
        raise NotImplementedError

    def export(self, destination: Path) -> dict[str, Any]:
        raise NotImplementedError

    def health(self) -> dict[str, Any]:
        raise NotImplementedError


def paths_for(home: Path, brain_id: str) -> VaultPaths:
    root = home / ".megabrain" / "vaults" / brain_id
    return VaultPaths(
        root=root,
        database=root / "vault.sqlite3",
        attachments=root / "attachments",
        runtime=root / "runtime",
        audit=root / "audit",
    )


def broker_socket_path(runtime: Path) -> Path:
    preferred = runtime / "broker.sock"
    if len(os.fsencode(preferred)) < 100:
        return preferred
    base = Path("/tmp") / f"megabrain-vault-{os.getuid()}"
    secure_directory(base)
    alias = base / hashlib.sha256(str(runtime).encode()).hexdigest()[:16]
    if alias.is_symlink() and alias.resolve() != runtime.resolve():
        alias.unlink()
    if not alias.exists():
        alias.symlink_to(runtime, target_is_directory=True)
    return alias / "broker.sock"


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        BEGIN IMMEDIATE;
        CREATE TABLE vault_header (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            schema_version INTEGER NOT NULL,
            vault_id TEXT NOT NULL UNIQUE,
            brain_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending_confirmation', 'active')),
            kdf_name TEXT NOT NULL,
            kdf_opslimit INTEGER NOT NULL,
            kdf_memlimit INTEGER NOT NULL,
            passphrase_salt BLOB NOT NULL,
            encrypted_master_key BLOB NOT NULL,
            master_key_nonce BLOB NOT NULL,
            recovery_master_key BLOB NOT NULL,
            recovery_nonce BLOB NOT NULL,
            suite TEXT NOT NULL
        );
        CREATE TABLE items (
            item_id TEXT PRIMARY KEY,
            resource_digest BLOB NOT NULL UNIQUE,
            encrypted_payload BLOB,
            payload_nonce BLOB,
            wrapped_item_key BLOB,
            key_nonce BLOB,
            item_version INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0 CHECK (deleted IN (0, 1))
        );
        CREATE INDEX items_active_digest ON items(resource_digest, deleted);
        CREATE TABLE attachments (
            attachment_id TEXT PRIMARY KEY,
            item_id TEXT NOT NULL REFERENCES items(item_id),
            encrypted_metadata BLOB,
            metadata_nonce BLOB,
            wrapped_file_key BLOB,
            key_nonce BLOB,
            blob_name TEXT NOT NULL UNIQUE,
            ciphertext_digest TEXT NOT NULL,
            created_at TEXT NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0 CHECK (deleted IN (0, 1))
        );
        CREATE INDEX attachments_item ON attachments(item_id, deleted);
        CREATE TABLE agent_grants (
            agent_id TEXT PRIMARY KEY,
            public_key BLOB NOT NULL,
            fingerprint TEXT NOT NULL,
            scopes_json TEXT NOT NULL,
            resource_classes_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
            granted_at TEXT NOT NULL,
            revoked_at TEXT,
            policy_version INTEGER NOT NULL
        );
        CREATE TABLE audit_events (
            event_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            agent_id TEXT,
            action TEXT NOT NULL,
            resource_digest BLOB,
            outcome TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            request_id TEXT
        );
        CREATE INDEX audit_timestamp ON audit_events(timestamp);
        CREATE TABLE broker_requests (
            request_id TEXT PRIMARY KEY,
            nonce TEXT NOT NULL UNIQUE,
            timestamp INTEGER NOT NULL,
            agent_id TEXT NOT NULL
        );
        PRAGMA user_version = 1;
        COMMIT;
        """
    )


def migrate_schema(connection: sqlite3.Connection, *, create: bool = False) -> None:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version == VAULT_SCHEMA_VERSION:
        return
    if version == 0 and create:
        try:
            create_schema(connection)
            return
        except sqlite3.DatabaseError:
            connection.rollback()
            raise
    raise VaultError("VAULT_FORMAT_UNSUPPORTED", "The Vault schema version is unsupported.")


class VaultStore(SensitiveStore):
    def __init__(self, paths: VaultPaths):
        self.paths = paths

    def connect(self) -> sqlite3.Connection:
        if not self.paths.database.exists():
            raise VaultError("VAULT_NOT_FOUND", "No Vault exists for this brain.")
        connection = sqlite3.connect(self.paths.database, factory=ClosingConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = DELETE")
        migrate_schema(connection)
        safe_permissions(self.paths.database, 0o600)
        return connection

    @contextlib.contextmanager
    def mutation_lock(self) -> Iterable[None]:
        """Serialize operations whose database and blob state must move together."""
        secure_directory(self.paths.runtime)
        descriptor = os.open(self.paths.runtime / "mutation.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @classmethod
    def setup(cls, paths: VaultPaths, brain_id: str, passphrase: str) -> tuple["VaultStore", str]:
        if paths.database.exists():
            raise VaultError("VAULT_EXISTS", "A Vault already exists for this brain.")
        for directory in (paths.root, paths.attachments, paths.runtime, paths.audit):
            secure_directory(directory)
        nacl = crypto()
        master_key = nacl.bindings.randombytes(32)
        recovery_key = nacl.bindings.randombytes(32)
        salt = nacl.bindings.randombytes(nacl.pwhash.argon2id.SALTBYTES)
        opslimit = int(nacl.pwhash.argon2id.OPSLIMIT_INTERACTIVE)
        memlimit = int(nacl.pwhash.argon2id.MEMLIMIT_INTERACTIVE)
        passphrase_key = derive_passphrase_key(passphrase, salt, opslimit, memlimit)
        vault_id = str(uuid.uuid4())
        wrapper_aad = f"megabrain.vault-master.v1:{vault_id}:{brain_id}:passphrase".encode()
        wrapped_master, master_nonce = encrypt(passphrase_key, master_key, wrapper_aad)
        recovery_aad = f"megabrain.vault-master.v1:{vault_id}:{brain_id}:recovery".encode()
        recovery_master, recovery_nonce = encrypt(recovery_key, master_key, recovery_aad)
        descriptor = os.open(paths.database, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        os.close(descriptor)
        try:
            connection = sqlite3.connect(paths.database)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = DELETE")
            migrate_schema(connection, create=True)
            connection.execute(
                """INSERT INTO vault_header (
                singleton,schema_version,vault_id,brain_id,created_at,status,kdf_name,kdf_opslimit,
                kdf_memlimit,passphrase_salt,encrypted_master_key,master_key_nonce,recovery_master_key,
                recovery_nonce,suite) VALUES
                (1, ?, ?, ?, ?, 'pending_confirmation', 'argon2id', ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    VAULT_SCHEMA_VERSION,
                    vault_id,
                    brain_id,
                    utc_now(),
                    opslimit,
                    memlimit,
                    salt,
                    wrapped_master,
                    master_nonce,
                    recovery_master,
                    recovery_nonce,
                    VAULT_SUITE,
                ),
            )
            connection.commit()
            connection.close()
            safe_permissions(paths.database, 0o600)
        except Exception:
            paths.database.unlink(missing_ok=True)
            raise
        return cls(paths), RECOVERY_PREFIX + b64(recovery_key)

    def header(self, connection: sqlite3.Connection) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM vault_header WHERE singleton = 1").fetchone()
        if row is None or row["schema_version"] != VAULT_SCHEMA_VERSION or row["suite"] != VAULT_SUITE:
            raise VaultError("VAULT_FORMAT_UNSUPPORTED", "The Vault format or cryptographic suite is unsupported.")
        return row

    def confirm_setup(self) -> None:
        with self.connect() as connection:
            header = self.header(connection)
            if header["status"] == "active":
                return
            connection.execute("UPDATE vault_header SET status = 'active' WHERE singleton = 1")

    def status(self) -> dict[str, Any]:
        if not self.paths.database.exists():
            return {"ok": True, "exists": False, "locked": True}
        with self.connect() as connection:
            header = self.header(connection)
            counts = {
                "items": connection.execute("SELECT count(*) FROM items WHERE deleted = 0").fetchone()[0],
                "attachments": connection.execute("SELECT count(*) FROM attachments WHERE deleted = 0").fetchone()[0],
                "active_grants": connection.execute("SELECT count(*) FROM agent_grants WHERE status = 'active'").fetchone()[0],
            }
        return {
            "ok": True,
            "exists": True,
            "ready": header["status"] == "active",
            "locked": not (self.paths.runtime / "broker.sock").exists(),
            "schema_version": header["schema_version"],
            "suite": header["suite"],
            "counts": counts,
        }

    def health(self) -> dict[str, Any]:
        return doctor(self)

    def attach(self, master_key: bytes, logical_id: str, source: Path) -> dict[str, Any]:
        return add_attachment(self, master_key, logical_id, source)

    def export(self, destination: Path) -> dict[str, Any]:
        return export_backup(self, destination)

    def unlock(self, *, passphrase: str | None = None, recovery_key: str | None = None) -> bytes:
        with self.connect() as connection:
            header = self.header(connection)
            if header["status"] != "active":
                raise VaultError("RECOVERY_CONFIRMATION_REQUIRED", "Confirm recovery material before using the Vault.")
            if passphrase is not None:
                try:
                    key = derive_passphrase_key(
                        passphrase,
                        bytes(header["passphrase_salt"]),
                        int(header["kdf_opslimit"]),
                        int(header["kdf_memlimit"]),
                    )
                    ciphertext = bytes(header["encrypted_master_key"])
                    nonce = bytes(header["master_key_nonce"])
                except (TypeError, ValueError, OverflowError) as error:
                    raise VaultError("VAULT_HEADER_INVALID", "Vault key-derivation parameters are invalid.") from error
                aad = f"megabrain.vault-master.v1:{header['vault_id']}:{header['brain_id']}:passphrase".encode()
                return decrypt(key, ciphertext, nonce, aad)
            if recovery_key is not None:
                key = recovery_bytes(recovery_key)
                try:
                    ciphertext = bytes(header["recovery_master_key"])
                    nonce = bytes(header["recovery_nonce"])
                except (TypeError, ValueError) as error:
                    raise VaultError("VAULT_HEADER_INVALID", "Vault recovery wrapper is invalid.") from error
                aad = f"megabrain.vault-master.v1:{header['vault_id']}:{header['brain_id']}:recovery".encode()
                return decrypt(key, ciphertext, nonce, aad)
        raise VaultError("UNLOCK_MATERIAL_REQUIRED", "Provide a passphrase or recovery key through standard input.")

    def resource_digest(self, master_key: bytes, logical_id: str) -> bytes:
        return hmac.new(master_key, normalize_logical_id(logical_id).encode(), hashlib.sha256).digest()

    def item_aad(self, item_id: str, digest: bytes, version: int, purpose: str) -> bytes:
        return b"|".join((ITEM_SCHEMA.encode(), item_id.encode(), digest.hex().encode(), str(version).encode(), purpose.encode()))

    def _row_for(self, connection: sqlite3.Connection, master_key: bytes, logical_id: str) -> sqlite3.Row:
        digest = self.resource_digest(master_key, logical_id)
        row = connection.execute(
            "SELECT * FROM items WHERE resource_digest = ? AND deleted = 0", (digest,)
        ).fetchone()
        if row is None:
            raise VaultError("ITEM_NOT_FOUND", "The requested Vault item was not found.")
        return row

    def _payload(self, master_key: bytes, row: sqlite3.Row) -> dict[str, Any]:
        try:
            digest = bytes(row["resource_digest"])
            wrapped_item_key = bytes(row["wrapped_item_key"])
            key_nonce = bytes(row["key_nonce"])
            encrypted_payload = bytes(row["encrypted_payload"])
            payload_nonce = bytes(row["payload_nonce"])
        except (TypeError, ValueError) as error:
            raise VaultError("AUTHENTICATION_FAILED", "Vault authentication failed.") from error
        aad_key = self.item_aad(row["item_id"], digest, row["item_version"], "key")
        item_key = decrypt(master_key, wrapped_item_key, key_nonce, aad_key)
        aad_payload = self.item_aad(row["item_id"], digest, row["item_version"], "payload")
        plaintext = decrypt(item_key, encrypted_payload, payload_nonce, aad_payload)
        try:
            payload = json.loads(plaintext)
        except json.JSONDecodeError as error:
            raise VaultError("CORRUPT_ITEM", "Vault item authentication failed.") from error
        if not isinstance(payload, dict) or payload.get("schema") != ITEM_SCHEMA:
            raise VaultError("CORRUPT_ITEM", "Vault item authentication failed.")
        return payload

    def put(self, master_key: bytes, item: dict[str, Any]) -> dict[str, Any]:
        logical_id = normalize_logical_id(item.get("logical_id"))
        item_type = item.get("type")
        label = item.get("label")
        fields = item.get("fields")
        if (
            not isinstance(item_type, str)
            or item_type not in ITEM_TYPE_FIELDS
            or not isinstance(label, str)
            or not label
            or len(label) > 128
            or any(ord(character) < 32 for character in label)
        ):
            raise VaultError("INVALID_ITEM", "Vault items require type and label fields.")
        if not isinstance(fields, dict) or not fields or not all(isinstance(key, str) for key in fields):
            raise VaultError("INVALID_ITEM", "Vault item fields must be a non-empty object.")
        if not set(fields) <= ITEM_TYPE_FIELDS[item_type]:
            raise VaultError("INVALID_ITEM_SCHEMA", "Vault item fields do not match the selected versioned item type.")
        digest = self.resource_digest(master_key, logical_id)
        now = utc_now()
        with self.connect() as connection:
            existing = connection.execute("SELECT * FROM items WHERE resource_digest = ?", (digest,)).fetchone()
            if existing and existing["deleted"]:
                raise VaultError("ITEM_DELETED", "A deleted logical resource cannot be silently recreated.")
            item_id = existing["item_id"] if existing else str(uuid.uuid4())
            version = int(existing["item_version"] + 1) if existing else 1
            created_at = existing["created_at"] if existing else now
            payload = {
                "schema": ITEM_SCHEMA,
                "logical_id": logical_id,
                "type": item_type,
                "label": label,
                "fields": fields,
                "created_at": created_at,
                "updated_at": now,
            }
            nacl = crypto()
            item_key = nacl.bindings.randombytes(32)
            wrapped_key, key_nonce = encrypt(
                master_key, item_key, self.item_aad(item_id, digest, version, "key")
            )
            try:
                serialized_payload = canonical(payload)
            except (TypeError, ValueError) as error:
                raise VaultError("INVALID_ITEM", "Vault item fields must contain valid JSON values.") from error
            encrypted_payload, payload_nonce = encrypt(
                item_key, serialized_payload, self.item_aad(item_id, digest, version, "payload")
            )
            if existing:
                connection.execute(
                    """UPDATE items SET encrypted_payload=?, payload_nonce=?, wrapped_item_key=?, key_nonce=?,
                    item_version=?, updated_at=? WHERE item_id=?""",
                    (encrypted_payload, payload_nonce, wrapped_key, key_nonce, version, now, item_id),
                )
            else:
                connection.execute(
                    "INSERT INTO items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                    (item_id, digest, encrypted_payload, payload_nonce, wrapped_key, key_nonce, version, now, now),
                )
            self.audit(connection, None, "put", digest, "allowed", "OWNER_AUTHORIZED", None)
        return {"ok": True, "created": existing is None, "item_id": item_id, "version": version}

    def metadata(self, master_key: bytes, logical_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = self._row_for(connection, master_key, logical_id)
            payload = self._payload(master_key, row)
        return {
            "ok": True,
            "item_id": row["item_id"],
            "type": payload["type"],
            "label": "[protected]",
            "masked_fields": mask_fields(payload["type"], payload["fields"]),
            "version": row["item_version"],
            "updated_at": row["updated_at"],
        }

    def reveal(self, master_key: bytes, logical_id: str, fields: Iterable[str]) -> dict[str, Any]:
        requested = list(fields)
        if not requested or not all(isinstance(field, str) and field for field in requested):
            raise VaultError("FIELD_REQUIRED", "Reveal requires an explicit field selection.")
        with self.connect() as connection:
            row = self._row_for(connection, master_key, logical_id)
            payload = self._payload(master_key, row)
        unknown = [field for field in requested if field not in payload["fields"]]
        if unknown:
            raise VaultError("FIELD_NOT_FOUND", "A requested Vault field was not found.")
        return {"ok": True, "item_id": row["item_id"], "fields": {field: payload["fields"][field] for field in requested}}

    def rotate_passphrase(self, master_key: bytes, new_passphrase: str) -> None:
        nacl = crypto()
        salt = nacl.bindings.randombytes(nacl.pwhash.argon2id.SALTBYTES)
        opslimit = int(nacl.pwhash.argon2id.OPSLIMIT_INTERACTIVE)
        memlimit = int(nacl.pwhash.argon2id.MEMLIMIT_INTERACTIVE)
        key = derive_passphrase_key(new_passphrase, salt, opslimit, memlimit)
        with self.connect() as connection:
            header = self.header(connection)
            aad = f"megabrain.vault-master.v1:{header['vault_id']}:{header['brain_id']}:passphrase".encode()
            wrapped, nonce = encrypt(key, master_key, aad)
            connection.execute(
                """UPDATE vault_header SET passphrase_salt=?, kdf_opslimit=?, kdf_memlimit=?,
                encrypted_master_key=?, master_key_nonce=? WHERE singleton=1""",
                (salt, opslimit, memlimit, wrapped, nonce),
            )
            self.audit(connection, None, "rotate-passphrase", None, "allowed", "OWNER_AUTHORIZED", None)

    def rotate_recovery(self, master_key: bytes, recovery: bytes | None = None) -> str:
        nacl = crypto()
        recovery = recovery if recovery is not None else nacl.bindings.randombytes(32)
        if len(recovery) != 32:
            raise VaultError("INVALID_RECOVERY_KEY", "Recovery material is invalid.")
        with self.connect() as connection:
            header = self.header(connection)
            aad = f"megabrain.vault-master.v1:{header['vault_id']}:{header['brain_id']}:recovery".encode()
            wrapped, nonce = encrypt(recovery, master_key, aad)
            connection.execute(
                "UPDATE vault_header SET recovery_master_key=?, recovery_nonce=? WHERE singleton=1",
                (wrapped, nonce),
            )
            self.audit(connection, None, "rotate-recovery", None, "allowed", "OWNER_AUTHORIZED", None)
        return RECOVERY_PREFIX + b64(recovery)

    def delete(self, master_key: bytes, logical_id: str) -> dict[str, Any]:
        blobs: list[str] = []
        with self.mutation_lock():
            with self.connect() as connection:
                row = self._row_for(connection, master_key, logical_id)
                digest = bytes(row["resource_digest"])
                blobs = [
                    result[0]
                    for result in connection.execute(
                        "SELECT blob_name FROM attachments WHERE item_id=? AND deleted=0", (row["item_id"],)
                    )
                ]
                connection.execute(
                    """UPDATE attachments SET deleted=1, encrypted_metadata=NULL, metadata_nonce=NULL,
                    wrapped_file_key=NULL, key_nonce=NULL WHERE item_id=?""",
                    (row["item_id"],),
                )
                connection.execute(
                    """UPDATE items SET deleted=1, encrypted_payload=NULL, payload_nonce=NULL,
                    wrapped_item_key=NULL, key_nonce=NULL WHERE item_id=?""",
                    (row["item_id"],),
                )
                self.audit(connection, None, "delete", digest, "allowed", "ACTIVE_KEY_DESTROYED", None)
            orphaned_blobs = 0
            for blob in blobs:
                try:
                    (self.paths.attachments / blob).unlink(missing_ok=True)
                except OSError:
                    orphaned_blobs += 1
        return {
            "ok": True,
            "deleted": True,
            "orphaned_encrypted_blobs": orphaned_blobs,
            "backup_notice": "Encrypted historical copies may remain in external backups until they are retired.",
        }

    def audit(
        self,
        connection: sqlite3.Connection,
        agent_id: str | None,
        action: str,
        digest: bytes | None,
        outcome: str,
        reason: str,
        request_id: str | None,
    ) -> None:
        connection.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), utc_now(), agent_id, action, digest, outcome, reason, request_id),
        )

    def audit_list(self, limit: int = 100) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT event_id,timestamp,agent_id,action,outcome,reason_code,request_id
                FROM audit_events ORDER BY rowid DESC LIMIT ?""",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return {"ok": True, "events": [dict(row) for row in rows]}


def mask_fields(item_type: str, fields: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, value in fields.items():
        text = str(value)
        if item_type in {"passport", "identity", "identity-document"} and name in {"document_number", "id_number"}:
            result[name] = "•" * 8 if len(text) < 5 else "•" * max(8, len(text) - 2) + text[-2:]
        elif item_type in {"credential", "credentials", "recovery-code"}:
            result[name] = "[protected]"
        elif name in {"expires_on", "issued_on"}:
            try:
                parsed = datetime.strptime(text, "%Y-%m-%d")
                result[name] = parsed.strftime("%Y-%m-%d") if len(text) == 10 else "[protected]"
            except (TypeError, ValueError):
                result[name] = "[protected]"
        else:
            result[name] = "[protected]"
    return result


def _attachment_aad(attachment_id: str, item_id: str, index: int, total: int, purpose: str) -> bytes:
    return f"megabrain.vault-attachment.v1|{attachment_id}|{item_id}|{index}|{total}|{purpose}".encode()


def add_attachment(
    store: VaultStore,
    master_key: bytes,
    logical_id: str,
    source: Path,
    *,
    filename: str | None = None,
    mime_type: str = "application/octet-stream",
) -> dict[str, Any]:
    selected_filename = filename if filename is not None else source.name
    if not isinstance(selected_filename, str) or not selected_filename or len(selected_filename) > 1024:
        raise VaultError("ATTACHMENT_METADATA", "Attachment filenames must be non-empty text under 1025 characters.")
    if not isinstance(mime_type, str) or not mime_type or len(mime_type) > 255:
        raise VaultError("ATTACHMENT_METADATA", "Attachment MIME types must be non-empty text under 256 characters.")
    try:
        size = source.stat().st_size
    except OSError as error:
        raise VaultError("ATTACHMENT_UNREADABLE", "The selected attachment could not be read.") from error
    if not source.is_file() or size > MAX_ATTACHMENT_SIZE:
        raise VaultError("ATTACHMENT_SIZE", "Attachments must be regular files no larger than 100 MiB.")
    with store.mutation_lock():
        nacl = crypto()
        with store.connect() as connection:
            item = store._row_for(connection, master_key, logical_id)
        attachment_id = str(uuid.uuid4())
        blob_name = f"{uuid.uuid4().hex}.mbva"
        total = max(1, (size + ATTACHMENT_CHUNK_SIZE - 1) // ATTACHMENT_CHUNK_SIZE)
        file_key = nacl.bindings.randombytes(32)
        wrapped_key, key_nonce = encrypt(
            master_key,
            file_key,
            _attachment_aad(attachment_id, item["item_id"], 0, total, "key"),
        )
        metadata = {
            "schema": "megabrain.vault-attachment.v1",
            "filename": selected_filename,
            "mime_type": mime_type,
            "size": size,
            "chunks": total,
        }
        encrypted_metadata, metadata_nonce = encrypt(
            file_key,
            canonical(metadata),
            _attachment_aad(attachment_id, item["item_id"], 0, total, "metadata"),
        )
        descriptor, temporary_name = tempfile.mkstemp(prefix=".attachment-", dir=store.paths.attachments)
        temporary = Path(temporary_name)
        digest = hashlib.sha256()
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as destination, source.open("rb") as origin:
                destination.write(ATTACHMENT_MAGIC)
                destination.write(struct.pack(">I", total))
                for index in range(total):
                    chunk = origin.read(ATTACHMENT_CHUNK_SIZE)
                    ciphertext, nonce = encrypt(
                        file_key,
                        chunk,
                        _attachment_aad(attachment_id, item["item_id"], index, total, "chunk"),
                    )
                    record = nonce + struct.pack(">I", len(ciphertext)) + ciphertext
                    destination.write(record)
                    digest.update(record)
                destination.flush()
                os.fsync(destination.fileno())
            final = store.paths.attachments / blob_name
            with store.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO attachments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                    (
                        attachment_id,
                        item["item_id"],
                        encrypted_metadata,
                        metadata_nonce,
                        wrapped_key,
                        key_nonce,
                        blob_name,
                        digest.hexdigest(),
                        utc_now(),
                    ),
                )
                os.replace(temporary, final)
                safe_permissions(final, 0o600)
                store.audit(connection, None, "attach", bytes(item["resource_digest"]), "allowed", "OWNER_AUTHORIZED", None)
                connection.commit()
            return {"ok": True, "attachment_id": attachment_id, "chunks": total}
        except Exception:
            temporary.unlink(missing_ok=True)
            (store.paths.attachments / blob_name).unlink(missing_ok=True)
            raise


def _extract_attachment_authenticated(
    store: VaultStore,
    master_key: bytes,
    attachment_id: str,
    destination: BinaryIO,
) -> dict[str, Any]:
    with store.connect() as connection:
        row = connection.execute(
            """SELECT a.*, i.resource_digest FROM attachments a JOIN items i ON i.item_id=a.item_id
            WHERE a.attachment_id=? AND a.deleted=0 AND i.deleted=0""",
            (attachment_id,),
        ).fetchone()
        if row is None:
            raise VaultError("ATTACHMENT_NOT_FOUND", "The requested encrypted attachment was not found.")
    blob = store.paths.attachments / row["blob_name"]
    try:
        source = blob.open("rb")
    except OSError as error:
        raise VaultError("ATTACHMENT_CORRUPT", "The encrypted attachment is missing or corrupt.") from error
    with source:
        if source.read(len(ATTACHMENT_MAGIC)) != ATTACHMENT_MAGIC:
            raise VaultError("ATTACHMENT_CORRUPT", "The encrypted attachment is missing or corrupt.")
        total_data = source.read(4)
        if len(total_data) != 4:
            raise VaultError("ATTACHMENT_CORRUPT", "The encrypted attachment is missing or corrupt.")
        total = struct.unpack(">I", total_data)[0]
        file_key = decrypt(
            master_key,
            bytes(row["wrapped_file_key"]),
            bytes(row["key_nonce"]),
            _attachment_aad(attachment_id, row["item_id"], 0, total, "key"),
        )
        try:
            metadata = json.loads(
                decrypt(
                    file_key,
                    bytes(row["encrypted_metadata"]),
                    bytes(row["metadata_nonce"]),
                    _attachment_aad(attachment_id, row["item_id"], 0, total, "metadata"),
                )
            )
        except json.JSONDecodeError as error:
            raise VaultError("ATTACHMENT_CORRUPT", "The encrypted attachment is missing or corrupt.") from error
        if (
            not isinstance(metadata, dict)
            or metadata.get("schema") != "megabrain.vault-attachment.v1"
            or metadata.get("chunks") != total
            or not isinstance(metadata.get("size"), int)
            or not 0 <= metadata["size"] <= MAX_ATTACHMENT_SIZE
            or not isinstance(metadata.get("mime_type"), str)
        ):
            raise VaultError("ATTACHMENT_CORRUPT", "The encrypted attachment is missing or corrupt.")
        digest = hashlib.sha256()
        authenticated_size = 0
        for index in range(total):
            nonce = source.read(24)
            length_data = source.read(4)
            if len(nonce) != 24 or len(length_data) != 4:
                raise VaultError("ATTACHMENT_CORRUPT", "The encrypted attachment is missing or corrupt.")
            length = struct.unpack(">I", length_data)[0]
            if not 16 <= length <= ATTACHMENT_CHUNK_SIZE + 16:
                raise VaultError("ATTACHMENT_CORRUPT", "The encrypted attachment is missing or corrupt.")
            ciphertext = source.read(length)
            if len(ciphertext) != length:
                raise VaultError("ATTACHMENT_CORRUPT", "The encrypted attachment is missing or corrupt.")
            digest.update(nonce + length_data + ciphertext)
            plaintext = decrypt(
                file_key,
                ciphertext,
                nonce,
                _attachment_aad(attachment_id, row["item_id"], index, total, "chunk"),
            )
            authenticated_size += len(plaintext)
        if source.read(1) or not hmac.compare_digest(digest.hexdigest(), row["ciphertext_digest"]):
            raise VaultError("ATTACHMENT_CORRUPT", "The encrypted attachment is missing or corrupt.")
        if authenticated_size != metadata["size"]:
            raise VaultError("ATTACHMENT_CORRUPT", "The encrypted attachment is missing or corrupt.")
        source.seek(len(ATTACHMENT_MAGIC) + 4)
        written = 0
        for index in range(total):
            nonce = source.read(24)
            length = struct.unpack(">I", source.read(4))[0]
            ciphertext = source.read(length)
            plaintext = decrypt(
                file_key,
                ciphertext,
                nonce,
                _attachment_aad(attachment_id, row["item_id"], index, total, "chunk"),
            )
            try:
                destination.write(plaintext)
            except OSError as error:
                raise VaultError("OUTPUT_FAILED", "The attachment output could not be written.") from error
            written += len(plaintext)
    return {"ok": True, "attachment_id": attachment_id, "size": written, "mime_type": metadata["mime_type"]}


def extract_attachment(
    store: VaultStore,
    master_key: bytes,
    attachment_id: str,
    destination: BinaryIO,
) -> dict[str, Any]:
    digest: bytes | None = None
    try:
        with store.connect() as connection:
            row = connection.execute(
                """SELECT i.resource_digest FROM attachments a JOIN items i ON i.item_id=a.item_id
                WHERE a.attachment_id=? AND a.deleted=0 AND i.deleted=0""",
                (attachment_id,),
            ).fetchone()
            if row is not None:
                digest = bytes(row["resource_digest"])
        result = _extract_attachment_authenticated(store, master_key, attachment_id, destination)
    except VaultError as error:
        try:
            with store.connect() as connection:
                store.audit(connection, None, "attachment-reveal", digest, "denied", error.code, None)
        except (VaultError, sqlite3.DatabaseError):
            pass
        raise
    with store.connect() as connection:
        store.audit(connection, None, "attachment-reveal", digest, "allowed", "OWNER_AUTHORIZED", None)
    return result


def agent_key_path(brain_root: Path) -> Path:
    return brain_root / ".megabrain" / "vault-agent-key.json"


def grant_agent(
    store: VaultStore,
    agent_id: str,
    brain_root: Path,
    scopes: list[str],
    classes: list[str],
) -> dict[str, Any]:
    try:
        uuid.UUID(agent_id)
    except (AttributeError, TypeError, ValueError) as error:
        raise VaultError("INVALID_AGENT", "A requesting agent identifier is required.")
    if not scopes or any(scope not in GLOBAL_SCOPES | RESOURCE_SCOPES for scope in scopes):
        raise VaultError("INVALID_SCOPE", "One or more requested Vault scopes are invalid.")
    if not all(isinstance(value, str) and value for value in classes):
        raise VaultError("INVALID_SCOPE", "Resource classes must be non-empty strings.")
    nacl = crypto()
    signing_key = nacl.signing.SigningKey.generate()
    verify_key = bytes(signing_key.verify_key)
    fingerprint = hashlib.sha256(verify_key).hexdigest()
    secure_json(
        agent_key_path(brain_root),
        {
            "schema": AGENT_KEY_SCHEMA,
            "agent_id": agent_id,
            "private_key": b64(bytes(signing_key)),
            "public_key_fingerprint": fingerprint,
        },
    )
    with store.connect() as connection:
        connection.execute(
            """INSERT INTO agent_grants VALUES (?, ?, ?, ?, ?, 'active', ?, NULL, 1)
            ON CONFLICT(agent_id) DO UPDATE SET public_key=excluded.public_key,
            fingerprint=excluded.fingerprint,scopes_json=excluded.scopes_json,
            resource_classes_json=excluded.resource_classes_json,status='active',
            granted_at=excluded.granted_at,revoked_at=NULL,policy_version=agent_grants.policy_version+1""",
            (
                agent_id,
                verify_key,
                fingerprint,
                json.dumps(sorted(set(scopes)), separators=(",", ":")),
                json.dumps(sorted(set(classes)), separators=(",", ":")),
                utc_now(),
            ),
        )
        store.audit(connection, agent_id, "grant", None, "allowed", "OWNER_AUTHORIZED", None)
    return {"ok": True, "agent_id": agent_id, "fingerprint": fingerprint, "scopes": sorted(set(scopes)), "resource_classes": sorted(set(classes))}


def revoke_agent(store: VaultStore, agent_id: str) -> dict[str, Any]:
    with store.connect() as connection:
        changed = connection.execute(
            "UPDATE agent_grants SET status='revoked',revoked_at=?,policy_version=policy_version+1 WHERE agent_id=?",
            (utc_now(), agent_id),
        ).rowcount
        store.audit(connection, agent_id, "revoke", None, "allowed", "OWNER_AUTHORIZED", None)
    if not changed:
        raise VaultError("AGENT_NOT_FOUND", "The Vault grant was not found.")
    return {"ok": True, "revoked": True, "agent_id": agent_id}


def signed_request(brain_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        key_data = json.loads(agent_key_path(brain_root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VaultError("AGENT_KEY_MISSING", "This agent has no local Vault signing key.") from error
    try:
        if key_data.get("schema") != AGENT_KEY_SCHEMA or len(str(key_data.get("agent_id", ""))) != 36:
            raise ValueError("invalid agent key metadata")
        uuid.UUID(key_data["agent_id"])
        private_key = unb64(key_data["private_key"])
        if len(private_key) != 32:
            raise ValueError("invalid agent private key")
    except (KeyError, TypeError, ValueError, VaultError) as error:
        raise VaultError("AGENT_KEY_INVALID", "The local Vault signing key is invalid.") from error
    nacl = crypto()
    request = {
        "schema": REQUEST_SCHEMA,
        "agent_id": key_data["agent_id"],
        "method": payload.get("method"),
        "resource": payload.get("resource"),
        "fields": payload.get("fields", []),
        "purpose": payload.get("purpose"),
        "context": payload.get("context", {"kind": "unknown"}),
        "timestamp": int(time.time()),
        "nonce": b64(nacl.bindings.randombytes(24)),
        "request_id": str(uuid.uuid4()),
    }
    signature = nacl.signing.SigningKey(private_key).sign(canonical(request)).signature
    request["signature"] = b64(signature)
    return request


def authorize_request(store: VaultStore, master_key: bytes, request: dict[str, Any], *, now: int | None = None) -> dict[str, Any]:
    now = int(time.time()) if now is None else now
    if not isinstance(request, dict):
        raise VaultError("MALFORMED_REQUEST", "The signed Vault request is invalid.")
    agent_id = request.get("agent_id") if isinstance(request.get("agent_id"), str) else None
    method = request.get("method") if isinstance(request.get("method"), str) else "unknown"
    request_id = request.get("request_id") if isinstance(request.get("request_id"), str) else None
    digest: bytes | None = None
    try:
        try:
            if len(agent_id or "") != 36:
                raise ValueError("invalid agent identifier")
            uuid.UUID(agent_id or "")
        except ValueError as error:
            raise VaultError("MALFORMED_REQUEST", "The signed Vault request is invalid.") from error
        if request.get("schema") != REQUEST_SCHEMA or not agent_id or method not in ACTION_SCOPES:
            raise VaultError("MALFORMED_REQUEST", "The signed Vault request is invalid.")
        resource = normalize_logical_id(request.get("resource"))
        digest = store.resource_digest(master_key, resource)
        timestamp = request.get("timestamp")
        nonce = request.get("nonce")
        if not isinstance(timestamp, int) or abs(now - timestamp) > MAX_CLOCK_SKEW_SECONDS:
            raise VaultError("STALE_REQUEST", "The signed Vault request is outside the accepted clock window.")
        try:
            if len(request_id or "") != 36 or len(nonce or "") != 32:
                raise ValueError("invalid request identifier length")
            uuid.UUID(request_id or "")
            decoded_nonce = unb64(nonce) if isinstance(nonce, str) else b""
        except (ValueError, VaultError):
            decoded_nonce = b""
        if not isinstance(nonce, str) or len(decoded_nonce) != 24 or not request_id:
            raise VaultError("MALFORMED_REQUEST", "The signed Vault request is invalid.")
        signature = request.get("signature")
        if not isinstance(signature, str) or len(signature) != 86:
            raise VaultError("SIGNATURE_INVALID", "The signed Vault request could not be authenticated.")
        unsigned = dict(request)
        unsigned.pop("signature", None)
        with store.connect() as connection:
            grant = connection.execute("SELECT * FROM agent_grants WHERE agent_id=?", (agent_id,)).fetchone()
            if grant is None:
                raise VaultError("AGENT_UNAUTHORIZED", "The requesting agent has no Vault grant.")
            if grant["status"] != "active":
                raise VaultError("AGENT_REVOKED", "The requesting agent's Vault grant is revoked.")
            nacl = crypto()
            try:
                nacl.signing.VerifyKey(bytes(grant["public_key"])).verify(canonical(unsigned), unb64(signature))
            except (nacl.exceptions.BadSignatureError, ValueError, VaultError) as error:
                raise VaultError("SIGNATURE_INVALID", "The signed Vault request could not be authenticated.") from error
            if connection.execute(
                "SELECT 1 FROM broker_requests WHERE request_id=? OR nonce=?", (request_id, nonce)
            ).fetchone():
                raise VaultError("REPLAY_REJECTED", "The signed Vault request was already used.")
            scopes = set(json.loads(grant["scopes_json"]))
            classes = set(json.loads(grant["resource_classes_json"]))
            required = ACTION_SCOPES[method]
            class_required = f"{resource_class(resource)}.{method if method in {'metadata', 'reveal'} else 'reveal'}"
            if required not in scopes or (method in {"metadata", "reveal"} and class_required not in scopes):
                raise VaultError("SCOPE_DENIED", "The requesting agent lacks the required Vault scope.")
            if classes and resource_class(resource) not in classes:
                raise VaultError("RESOURCE_CLASS_DENIED", "The requesting agent is not granted this resource class.")
            if method == "reveal":
                raise VaultError(
                    "PRIVATE_CONTEXT_UNATTESTED",
                    "Agent reveal is disabled until the harness can independently attest a private context.",
                )
            purpose = request.get("purpose")
            if method == "reveal" and (
                not isinstance(purpose, str) or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", purpose) is None
            ):
                raise VaultError("PURPOSE_REQUIRED", "Vault reveal requires a structured purpose code.")
            connection.execute("DELETE FROM broker_requests WHERE timestamp < ?", (now - MAX_CLOCK_SKEW_SECONDS,))
            connection.execute(
                "INSERT INTO broker_requests VALUES (?, ?, ?, ?)", (request_id, nonce, timestamp, agent_id)
            )
        return {
            "resource": resource,
            "resource_digest": digest,
            "method": method,
            "fields": request.get("fields", []),
            "agent_id": agent_id,
            "request_id": request_id,
        }
    except VaultError as error:
        try:
            with store.connect() as connection:
                store.audit(connection, agent_id, method, digest, "denied", error.code, request_id)
        except VaultError:
            pass
        raise


def broker_socket_request(socket_path: Path, request: dict[str, Any]) -> dict[str, Any]:
    socket_path = broker_socket_path(socket_path.parent)
    if not socket_path.exists():
        raise VaultError("VAULT_LOCKED", "The Vault is locked.")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.settimeout(5)
        client.connect(str(socket_path))
        client.sendall(canonical(request) + b"\n")
        chunks = bytearray()
        while not chunks.endswith(b"\n") and len(chunks) <= 1024 * 1024:
            part = client.recv(65536)
            if not part:
                break
            chunks.extend(part)
        result = json.loads(chunks)
        if not isinstance(result, dict):
            raise ValueError("broker response is not an object")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise VaultError("BROKER_UNAVAILABLE", "The local Vault broker is unavailable.") from error
    finally:
        client.close()
    if not result.get("ok"):
        error = result.get("error", {})
        if not isinstance(error, dict):
            raise VaultError("BROKER_ERROR", "Vault request failed.")
        raise VaultError(str(error.get("code", "BROKER_ERROR")), str(error.get("message", "Vault request failed.")))
    return result


def serve_broker(store: VaultStore, master_key: bytes, idle_timeout: int = 300) -> None:
    if not 5 <= idle_timeout <= 3600:
        raise VaultError("INVALID_TIMEOUT", "Vault idle timeout must be between 5 and 3600 seconds.")
    socket_path = broker_socket_path(store.paths.runtime)
    lock_descriptor = os.open(store.paths.runtime / "broker.lock", os.O_CREAT | os.O_RDWR, 0o600)
    os.fchmod(lock_descriptor, 0o600)
    try:
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        os.close(lock_descriptor)
        raise VaultError("BROKER_ALREADY_RUNNING", "The Vault broker is already running.") from error
    socket_path.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    last_activity = time.monotonic()
    try:
        server.bind(str(socket_path))
        safe_permissions(socket_path, 0o600)
        server.listen(8)
        server.settimeout(1)
        secure_json(store.paths.runtime / "broker.json", {"pid": os.getpid(), "started_at": utc_now(), "idle_timeout": idle_timeout})
        while time.monotonic() - last_activity < idle_timeout:
            try:
                client, _ = server.accept()
            except socket.timeout:
                continue
            with client:
                authorized: dict[str, Any] | None = None
                try:
                    data = bytearray()
                    while not data.endswith(b"\n"):
                        remaining = idle_timeout - (time.monotonic() - last_activity)
                        if remaining <= 0:
                            raise VaultError("BROKER_IDLE_TIMEOUT", "The Vault broker locked after inactivity.")
                        client.settimeout(min(1.0, remaining))
                        part = client.recv(65536)
                        if not part:
                            break
                        data.extend(part)
                        if len(data) > 1024 * 1024:
                            raise VaultError("REQUEST_TOO_LARGE", "The broker request exceeds the size limit.")
                    request = json.loads(data)
                    if not isinstance(request, dict):
                        raise VaultError("MALFORMED_REQUEST", "The broker request is invalid.")
                    if request.get("method") == "owner.status":
                        client.sendall(canonical({"ok": True, "unlocked": True}) + b"\n")
                        continue
                    if request.get("method") == "owner.lock":
                        client.sendall(canonical({"ok": True, "locked": True}) + b"\n")
                        break
                    authorized = authorize_request(store, master_key, request)
                    if authorized["method"] == "metadata":
                        result = store.metadata(master_key, authorized["resource"])
                    else:
                        raise VaultError("METHOD_UNSUPPORTED", "The broker method is not implemented.")
                    with store.connect() as connection:
                        store.audit(
                            connection,
                            authorized["agent_id"],
                            authorized["method"],
                            authorized["resource_digest"],
                            "allowed",
                            "OPERATION_SUCCEEDED",
                            authorized["request_id"],
                        )
                    last_activity = time.monotonic()
                    client.sendall(canonical(result) + b"\n")
                except (VaultError, json.JSONDecodeError, socket.timeout) as error:
                    if isinstance(error, VaultError) and authorized is not None:
                        try:
                            with store.connect() as connection:
                                store.audit(
                                    connection,
                                    authorized["agent_id"],
                                    authorized["method"],
                                    authorized["resource_digest"],
                                    "denied",
                                    error.code,
                                    authorized["request_id"],
                                )
                        except VaultError:
                            pass
                    if isinstance(error, VaultError):
                        payload = {"ok": False, "error": {"code": error.code, "message": error.message}}
                    elif isinstance(error, socket.timeout):
                        payload = {"ok": False, "error": {"code": "REQUEST_TIMEOUT", "message": "The broker request timed out."}}
                    else:
                        payload = {"ok": False, "error": {"code": "MALFORMED_REQUEST", "message": "The broker request is invalid."}}
                    try:
                        client.sendall(canonical(payload) + b"\n")
                    except OSError:
                        pass
    finally:
        server.close()
        socket_path.unlink(missing_ok=True)
        (store.paths.runtime / "broker.json").unlink(missing_ok=True)
        fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        os.close(lock_descriptor)


def lock_broker(store: VaultStore) -> dict[str, Any]:
    socket_path = broker_socket_path(store.paths.runtime)
    if not socket_path.exists():
        return {"ok": True, "locked": True, "already_locked": True}
    return broker_socket_request(socket_path, {"method": "owner.lock"})


def export_backup(store: VaultStore, destination: Path) -> dict[str, Any]:
    if destination.exists():
        raise VaultError("BACKUP_EXISTS", "The backup destination already exists.")
    if not destination.parent.is_dir():
        raise VaultError("BACKUP_DESTINATION_INVALID", "The backup destination directory does not exist.")
    descriptor, snapshot_name = tempfile.mkstemp(prefix=".vault-snapshot-", dir=store.paths.root)
    os.close(descriptor)
    snapshot = Path(snapshot_name)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with store.mutation_lock():
            source = store.connect()
            target = sqlite3.connect(snapshot)
            source.backup(target)
            target.close()
            source.close()
            safe_permissions(snapshot, 0o600)
            files: list[tuple[str, Path]] = [("vault.sqlite3", snapshot)]
            snapshot_connection = sqlite3.connect(snapshot)
            snapshot_connection.row_factory = sqlite3.Row
            try:
                for row in snapshot_connection.execute("SELECT blob_name FROM attachments WHERE deleted=0"):
                    blob = store.paths.attachments / row["blob_name"]
                    if not blob.exists():
                        raise VaultError("ATTACHMENT_CORRUPT", "An encrypted attachment is missing.")
                    files.append((f"attachments/{row['blob_name']}", blob))
                header = snapshot_connection.execute("SELECT * FROM vault_header WHERE singleton=1").fetchone()
            finally:
                snapshot_connection.close()
            manifest = {
                "schema": BACKUP_SCHEMA,
                "version": 1,
                "vault_id": header["vault_id"],
                "brain_id": header["brain_id"],
                "created_at": utc_now(),
                "files": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files},
            }
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("manifest.json", canonical(manifest))
                for name, path in files:
                    archive.write(path, name)
            safe_permissions(temporary, 0o600)
            os.replace(temporary, destination)
            return {"ok": True, "path": str(destination), "files": len(files), "vault_id": header["vault_id"]}
    finally:
        snapshot.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)


def _safe_backup_names(archive: zipfile.ZipFile) -> set[str]:
    entries = archive.infolist()
    names = {entry.filename for entry in entries}
    if len(entries) > MAX_BACKUP_FILES or len(names) != len(entries):
        raise VaultError("BACKUP_INVALID", "The Vault backup inventory is invalid.")
    expanded = 0
    for entry in entries:
        name = entry.filename
        path = Path(name)
        maximum = (
            MAX_BACKUP_MANIFEST_SIZE
            if name == "manifest.json"
            else MAX_BACKUP_DATABASE_SIZE
            if name == "vault.sqlite3"
            else MAX_ATTACHMENT_SIZE + 1024 * 1024
        )
        expanded += entry.file_size
        if (
            entry.compress_type != zipfile.ZIP_STORED
            or entry.is_dir()
            or entry.file_size > maximum
            or expanded > MAX_BACKUP_EXPANDED_SIZE
            or path.is_absolute()
            or ".." in path.parts
            or (name != "manifest.json" and name != "vault.sqlite3" and not name.startswith("attachments/"))
        ):
            raise VaultError("BACKUP_INVALID", "The Vault backup contains an unsafe path.")
    return names


class DiscardWriter:
    def write(self, value: bytes) -> int:
        return len(value)


def restore_backup(
    backup: Path,
    destination_paths: VaultPaths,
    *,
    passphrase: str | None = None,
    recovery_key: str | None = None,
) -> dict[str, Any]:
    if destination_paths.root.exists():
        raise VaultError("VAULT_EXISTS", "Restore refuses to overwrite an existing Vault.")
    parent = destination_paths.root.parent
    secure_directory(parent)
    temporary_root = Path(tempfile.mkdtemp(prefix=".restore-", dir=parent))
    safe_permissions(temporary_root, 0o700)
    try:
        try:
            archive = zipfile.ZipFile(backup, "r")
        except (OSError, zipfile.BadZipFile) as error:
            raise VaultError("BACKUP_INVALID", "The Vault backup is invalid or corrupt.") from error
        with archive:
            names = _safe_backup_names(archive)
            try:
                manifest = json.loads(archive.read("manifest.json"))
            except (KeyError, json.JSONDecodeError) as error:
                raise VaultError("BACKUP_INVALID", "The Vault backup manifest is invalid.") from error
            if manifest.get("schema") != BACKUP_SCHEMA or manifest.get("version") != 1:
                raise VaultError("BACKUP_UNSUPPORTED", "The Vault backup format is unsupported.")
            if manifest.get("brain_id") != destination_paths.root.name:
                raise VaultError("BACKUP_BRAIN_MISMATCH", "The Vault backup belongs to a different brain identifier.")
            expected = manifest.get("files")
            if not isinstance(expected, dict) or set(expected) | {"manifest.json"} != names:
                raise VaultError("BACKUP_INVALID", "The Vault backup inventory is inconsistent.")
            for name, digest in expected.items():
                if not isinstance(name, str) or not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                    raise VaultError("BACKUP_INVALID", "The Vault backup inventory is inconsistent.")
                destination = temporary_root / name
                secure_directory(destination.parent)
                descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                calculated = hashlib.sha256()
                with archive.open(name) as source, os.fdopen(descriptor, "wb") as stream:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        calculated.update(chunk)
                        stream.write(chunk)
                if not hmac.compare_digest(calculated.hexdigest(), digest):
                    raise VaultError("BACKUP_CORRUPT", "Vault backup integrity verification failed.")
        temporary_paths = VaultPaths(
            root=temporary_root,
            database=temporary_root / "vault.sqlite3",
            attachments=temporary_root / "attachments",
            runtime=temporary_root / "runtime",
            audit=temporary_root / "audit",
        )
        secure_directory(temporary_paths.attachments)
        secure_directory(temporary_paths.runtime)
        secure_directory(temporary_paths.audit)
        restored = VaultStore(temporary_paths)
        master_key = restored.unlock(passphrase=passphrase, recovery_key=recovery_key)
        with restored.connect() as connection:
            header = restored.header(connection)
            if header["brain_id"] != manifest["brain_id"] or header["vault_id"] != manifest["vault_id"]:
                raise VaultError("BACKUP_INVALID", "The Vault backup identity is inconsistent.")
            rows = connection.execute("SELECT * FROM items WHERE deleted=0").fetchall()
            for row in rows:
                restored._payload(master_key, row)
            attachment_ids = [row[0] for row in connection.execute("SELECT attachment_id FROM attachments WHERE deleted=0")]
            active_blobs = {row[0] for row in connection.execute("SELECT blob_name FROM attachments WHERE deleted=0")}
        actual_blobs = {path.name for path in temporary_paths.attachments.iterdir() if path.is_file()}
        if active_blobs != actual_blobs:
            raise VaultError("BACKUP_INVALID", "The Vault backup attachment inventory is inconsistent.")
        for attachment_id in attachment_ids:
            extract_attachment(restored, master_key, attachment_id, DiscardWriter())
        os.replace(temporary_root, destination_paths.root)
        return {"ok": True, "restored": True, "vault_id": manifest["vault_id"], "items": len(rows)}
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


def doctor(store: VaultStore) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    try:
        nacl = crypto()
        checks.append({"name": "dependency", "ok": True, "version": nacl.__version__})
    except VaultError as error:
        checks.append({"name": "dependency", "ok": False, "code": error.code})
    for path, expected in (
        (store.paths.root, 0o700),
        (store.paths.attachments, 0o700),
        (store.paths.runtime, 0o700),
        (store.paths.audit, 0o700),
        (store.paths.database, 0o600),
    ):
        exists = path.exists()
        mode = path.stat().st_mode & 0o777 if exists else None
        checks.append({"name": f"permissions:{path.name}", "ok": exists and mode == expected, "mode": oct(mode) if mode is not None else None})
    orphans: list[str] = []
    try:
        with store.connect() as connection:
            header = store.header(connection)
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            grants = connection.execute("SELECT count(*) FROM agent_grants WHERE status='active'").fetchone()[0]
            known = {row[0] for row in connection.execute("SELECT blob_name FROM attachments WHERE deleted=0")}
        actual = {path.name for path in store.paths.attachments.iterdir() if path.is_file() and not path.name.startswith(".")}
        orphans = sorted(actual - known)
        checks.extend(
            (
                {"name": "schema", "ok": header["schema_version"] == VAULT_SCHEMA_VERSION},
                {"name": "suite", "ok": header["suite"] == VAULT_SUITE},
                {"name": "sqlite_integrity", "ok": integrity},
                {"name": "grant_consistency", "ok": grants >= 0},
                {"name": "orphaned_blobs", "ok": not orphans, "count": len(orphans)},
                {"name": "broker", "ok": True, "locked": not (store.paths.runtime / "broker.sock").exists()},
            )
        )
    except (VaultError, sqlite3.DatabaseError):
        checks.append({"name": "database", "ok": False, "code": "VAULT_CORRUPT"})
    return {"ok": all(check["ok"] for check in checks), "checks": checks, "orphan_count": len(orphans)}
