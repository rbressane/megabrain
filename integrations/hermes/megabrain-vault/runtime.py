"""Trusted Hermes boundary for attested MegaBrain Vault delivery.

The model-facing handler never accepts provenance, approval, destination, key,
or value fields. A live gateway turn is captured by a host hook, cross-checked
against post-authorization task-local ContextVars, and converted to a short
pending approval. The owner approves that exact request with a slash command;
the slash handler signs, asks Vault for a sealed release, and delivers it from a
trusted adapter without returning plaintext or ciphertext to the model.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import socket
import stat
import struct
import sys
import tempfile
import threading
import time
import uuid
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


STATE_SCHEMA = "megabrain.hermes-harness-state.v1"
CONTROL_SCHEMA = "megabrain.hermes-harness-control.v1"
STATE_AAD = STATE_SCHEMA.encode("ascii")
PENDING_TTL = 45
MAX_PENDING = 100
_TURN: ContextVar["TurnCandidate | None"] = ContextVar("megabrain_hermes_turn", default=None)
_STATE_LOCK = threading.RLock()
_PENDING_LOCK = threading.RLock()
_AUTHORITY: Any = None
_UNLOCKED_STATE: dict[str, Any] | None = None
_PENDING: dict[str, "PendingApproval"] = {}


def _hermes_home() -> Path:
    configured = os.environ.get("HERMES_HOME")
    return Path(configured).expanduser().resolve() if configured else (Path.home() / ".hermes").resolve()


def _plugin_root() -> Path:
    return _hermes_home() / "megabrain-vault"


def _state_path() -> Path:
    return _plugin_root() / "state.json"


def _control_path() -> Path:
    runtime = _plugin_root() / "runtime"
    _secure_directory(runtime)
    _, vault, _ = _core()
    return vault.broker_socket_path(runtime).with_name("harness.sock")


def _runtime_scripts() -> Path:
    return (Path.home() / ".megabrain" / "runtime" / "current" / "skill" / "megabrain" / "scripts").resolve()


def _core() -> tuple[Any, Any, Any]:
    scripts = _runtime_scripts()
    if not (scripts / "vault.py").is_file() or not (scripts / "vault_delivery.py").is_file():
        raise RuntimeError("A MegaBrain 1.2-compatible runtime is not installed.")
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import megabrain
    import vault
    import vault_delivery

    return megabrain, vault, vault_delivery


def _secure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    state = os.lstat(path)
    if stat.S_ISLNK(state.st_mode) or not stat.S_ISDIR(state.st_mode) or state.st_uid != os.getuid():
        raise RuntimeError("The Hermes harness state directory is unsafe.")
    os.chmod(path, 0o700)


def _write_json_private(path: Path, value: Mapping[str, Any]) -> None:
    _secure_directory(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _state_key(passphrase: str, salt: bytes, opslimit: int, memlimit: int) -> bytes:
    _, vault, _ = _core()
    return vault.derive_passphrase_key(passphrase, salt, opslimit, memlimit)


def _authority_record(authority: Any, vault: Any) -> dict[str, str]:
    return {
        "issuer_instance": authority.issuer_instance,
        "key_id": authority.key_id,
        "signing_key": vault.b64(authority.signing_key),
        "digest_key": vault.b64(authority.digest_key),
    }


def _authority_from_record(record: Mapping[str, Any], vault: Any, delivery: Any) -> Any:
    if not isinstance(record, Mapping) or set(record) != {
        "issuer_instance", "key_id", "signing_key", "digest_key"
    }:
        raise RuntimeError("The encrypted Hermes harness state is invalid.")
    return delivery.HarnessAuthority(
        issuer_instance=str(record["issuer_instance"]),
        key_id=str(record["key_id"]),
        signing_key=vault.unb64(str(record["signing_key"])),
        digest_key=vault.unb64(str(record["digest_key"])),
    ).validated()


def _encrypt_state(inner: Mapping[str, Any], passphrase: str) -> dict[str, Any]:
    _, vault, _ = _core()
    nacl = vault.crypto()
    salt = nacl.bindings.randombytes(nacl.pwhash.argon2id.SALTBYTES)
    opslimit = int(nacl.pwhash.argon2id.OPSLIMIT_INTERACTIVE)
    memlimit = int(nacl.pwhash.argon2id.MEMLIMIT_INTERACTIVE)
    key = _state_key(passphrase, salt, opslimit, memlimit)
    ciphertext, nonce = vault.encrypt(key, vault.canonical(dict(inner)), STATE_AAD)
    return {
        "schema": STATE_SCHEMA,
        "kdf_salt": vault.b64(salt),
        "kdf_opslimit": opslimit,
        "kdf_memlimit": memlimit,
        "nonce": vault.b64(nonce),
        "ciphertext": vault.b64(ciphertext),
    }


def _decrypt_state(passphrase: str) -> dict[str, Any]:
    _, vault, _ = _core()
    path = _state_path()
    state = os.lstat(path)
    if stat.S_ISLNK(state.st_mode) or not stat.S_ISREG(state.st_mode) or state.st_uid != os.getuid():
        raise RuntimeError("The Hermes harness state file is unsafe.")
    if stat.S_IMODE(state.st_mode) != 0o600:
        raise RuntimeError("The Hermes harness state file must be mode 0600.")
    outer = json.loads(path.read_text(encoding="utf-8"))
    expected = {"schema", "kdf_salt", "kdf_opslimit", "kdf_memlimit", "nonce", "ciphertext"}
    if not isinstance(outer, dict) or set(outer) != expected or outer.get("schema") != STATE_SCHEMA:
        raise RuntimeError("The encrypted Hermes harness state is invalid.")
    key = _state_key(
        passphrase,
        vault.unb64(outer["kdf_salt"]),
        int(outer["kdf_opslimit"]),
        int(outer["kdf_memlimit"]),
    )
    plaintext = vault.decrypt(
        key,
        vault.unb64(outer["ciphertext"]),
        vault.unb64(outer["nonce"]),
        STATE_AAD,
    )
    inner = json.loads(plaintext)
    if not isinstance(inner, dict):
        raise RuntimeError("The encrypted Hermes harness state is invalid.")
    return inner


def _save_state(inner: Mapping[str, Any], passphrase: str) -> None:
    _write_json_private(_state_path(), _encrypt_state(inner, passphrase))


def _active_authority(inner: Mapping[str, Any]) -> Any:
    _, vault, delivery = _core()
    active = inner.get("active_key_id")
    records = inner.get("authorities")
    if not isinstance(active, str) or not isinstance(records, list):
        raise RuntimeError("The encrypted Hermes harness state has no active key.")
    for record in records:
        if isinstance(record, Mapping) and record.get("key_id") == active:
            return _authority_from_record(record, vault, delivery)
    raise RuntimeError("The encrypted Hermes harness state has no active key.")


def _set_unlocked(inner: dict[str, Any], authority: Any) -> None:
    global _AUTHORITY, _UNLOCKED_STATE
    with _STATE_LOCK:
        _AUTHORITY = authority
        _UNLOCKED_STATE = {
            key: inner[key]
            for key in ("brain_root", "brain_id", "agent_id", "active_key_id")
            if key in inner
        }


def _lock_memory() -> None:
    global _AUTHORITY, _UNLOCKED_STATE
    with _STATE_LOCK:
        if isinstance(_UNLOCKED_STATE, dict):
            _UNLOCKED_STATE.clear()
        _AUTHORITY = None
        _UNLOCKED_STATE = None
    with _PENDING_LOCK:
        _PENDING.clear()


def _snapshot() -> tuple[Any, dict[str, Any]]:
    with _STATE_LOCK:
        if _AUTHORITY is None or _UNLOCKED_STATE is None:
            raise RuntimeError("The Hermes harness key is locked. Use the owner-local unlock command.")
        return _AUTHORITY, dict(_UNLOCKED_STATE)


def _vault_store(brain_root: Path) -> tuple[Any, str]:
    _, vault, _ = _core()
    manifest = json.loads((brain_root / "megabrain.json").read_text(encoding="utf-8"))
    brain_id = manifest.get("brain_id")
    if not isinstance(brain_id, str):
        raise RuntimeError("The selected Brain has no stable brain_id.")
    return vault.VaultStore(vault.paths_for(Path.home(), brain_id)), brain_id


def _agent_id(brain_root: Path) -> str:
    identity = json.loads((brain_root / ".megabrain" / "local.json").read_text(encoding="utf-8"))
    value = identity.get("id")
    uuid.UUID(str(value))
    return str(value)


@dataclass(frozen=True)
class TurnCandidate:
    gateway: Any
    source: Any
    loop: asyncio.AbstractEventLoop
    platform: str
    chat_type: str
    user_id: str
    chat_id: str
    thread_id: str
    message_id: str
    session_key: str
    internal: bool

    def stable_destination(self) -> dict[str, str]:
        return {
            "platform": self.platform,
            "chat_type": self.chat_type,
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "thread_id": self.thread_id,
        }


@dataclass(frozen=True)
class PendingApproval:
    approval_id: str
    request_id: str
    request: dict[str, Any]
    prompt: dict[str, Any]
    issued_at: int
    expires_at: int
    stable_destination: dict[str, str]
    key_id: str
    brain_id: str
    agent_id: str
    delivery_policy: str
    capability: dict[str, Any] | None


def _platform_value(source: Any) -> str:
    platform = getattr(source, "platform", "")
    return str(getattr(platform, "value", platform) or "")


def _capture_turn(*, event: Any, gateway: Any, session_store: Any = None, **_: Any) -> None:
    _CONTROL.ensure_started()
    source = getattr(event, "source", None)
    if source is None:
        _TURN.set(None)
        return
    try:
        loop = asyncio.get_running_loop()
        session_key = str(gateway._session_key_for_source(source))
    except Exception:
        _TURN.set(None)
        return
    _TURN.set(TurnCandidate(
        gateway=gateway,
        source=source,
        loop=loop,
        platform=_platform_value(source),
        chat_type=str(getattr(source, "chat_type", "") or ""),
        user_id=str(getattr(source, "user_id", "") or ""),
        chat_id=str(getattr(source, "chat_id", "") or ""),
        thread_id=str(getattr(source, "thread_id", "") or ""),
        message_id=str(getattr(source, "message_id", "") or ""),
        session_key=session_key,
        internal=bool(getattr(event, "internal", False)),
    ))


def _host_context(kwargs: Mapping[str, Any], agent_id: str) -> tuple[Any, TurnCandidate]:
    _, _, delivery = _core()
    try:
        from gateway.session_context import _VAR_MAP, get_session_env
    except Exception as error:
        raise RuntimeError("Hermes trusted session provenance is unavailable.") from error
    if not {"HERMES_SESSION_SOURCE", "HERMES_SESSION_CHAT_TYPE"} <= set(_VAR_MAP):
        raise RuntimeError("Hermes trusted session provenance is unavailable.")
    candidate = _TURN.get()
    if candidate is None or candidate.internal:
        raise RuntimeError("PRIVATE_CONTEXT_UNATTESTED")
    bound = {
        "source_kind": get_session_env("HERMES_SESSION_SOURCE", ""),
        "platform": get_session_env("HERMES_SESSION_PLATFORM", ""),
        "chat_type": get_session_env("HERMES_SESSION_CHAT_TYPE", ""),
        "user_id": get_session_env("HERMES_SESSION_USER_ID", ""),
        "chat_id": get_session_env("HERMES_SESSION_CHAT_ID", ""),
        "thread_id": get_session_env("HERMES_SESSION_THREAD_ID", ""),
        "message_id": get_session_env("HERMES_SESSION_MESSAGE_ID", ""),
        "session_id": get_session_env("HERMES_SESSION_ID", ""),
    }
    expected = {
        "platform": candidate.platform,
        "chat_type": candidate.chat_type,
        "user_id": candidate.user_id,
        "chat_id": candidate.chat_id,
        "thread_id": candidate.thread_id,
        "message_id": candidate.message_id,
    }
    handler_session = kwargs.get("session_id")
    if (
        bound["source_kind"] != "gateway_user"
        or bound["chat_type"] != "dm"
        or any(bound[key] != value for key, value in expected.items())
        or not isinstance(handler_session, str)
        or not handler_session
        or handler_session != bound["session_id"]
    ):
        raise RuntimeError("PRIVATE_CONTEXT_UNATTESTED")
    context = delivery.TrustedContext(
        source_kind=bound["source_kind"],
        platform=bound["platform"],
        chat_type=bound["chat_type"],
        user_id=bound["user_id"],
        chat_id=bound["chat_id"],
        thread_id=bound["thread_id"],
        session_id=bound["session_id"],
        message_id=bound["message_id"],
        agent_id=agent_id,
    ).validated()
    return context, candidate


def _command_context(candidate: TurnCandidate, agent_id: str) -> Any:
    _, _, delivery = _core()
    if (
        candidate.internal
        or candidate.chat_type != "dm"
        or not candidate.platform
        or candidate.platform in {"email", "api_server"}
        or not candidate.user_id
        or not candidate.chat_id
        or not candidate.message_id
    ):
        raise RuntimeError("PRIVATE_CONTEXT_UNATTESTED")
    return delivery.TrustedContext(
        source_kind="gateway_user",
        platform=candidate.platform,
        chat_type=candidate.chat_type,
        user_id=candidate.user_id,
        chat_id=candidate.chat_id,
        thread_id=candidate.thread_id,
        session_id=candidate.session_key,
        message_id=candidate.message_id,
        agent_id=agent_id,
    ).validated()


def _broker_ready(store: Any) -> bool:
    try:
        _, vault, _ = _core()
        result = vault.broker_socket_request(
            vault.broker_socket_path(store.paths.runtime),
            {"method": "owner.status"},
        )
        return result.get("unlocked") is True
    except Exception:
        return False


def _tool_available() -> bool:
    try:
        _, state = _snapshot()
        store, _ = _vault_store(Path(state["brain_root"]))
        from gateway.session_context import _VAR_MAP, get_session_env
        return (
            {"HERMES_SESSION_SOURCE", "HERMES_SESSION_CHAT_TYPE"} <= set(_VAR_MAP)
            and get_session_env("HERMES_SESSION_SOURCE", "") == "gateway_user"
            and get_session_env("HERMES_SESSION_CHAT_TYPE", "") == "dm"
            and _broker_ready(store)
        )
    except Exception:
        return False


def _policy_and_capability(request: Mapping[str, Any]) -> tuple[str, dict[str, Any] | None]:
    if request["action"] == "use":
        return "direct_use_only", {
            "capability_id": "synthetic.token-check",
            "adapter_id": "synthetic.token-check",
            "host": "api.example.invalid",
            "operation": "token-check",
            "fields": list(request["fields"]),
            "timeout_seconds": 5,
        }
    return "private_dm_opt_in", None


def _metadata(request: Mapping[str, Any], state: Mapping[str, Any]) -> str:
    megabrain, _, _ = _core()
    result = megabrain.command_vault(
        Path(state["brain_root"]),
        "metadata",
        {
            "resource": request["resource"],
            "fields": request["fields"],
            "purpose": request["purpose"],
            "context": {"kind": "unknown"},
        },
    )
    return json.dumps(result, ensure_ascii=True, sort_keys=True)


def _queue_approval(request: Mapping[str, Any], context: Any, candidate: TurnCandidate) -> str:
    authority, state = _snapshot()
    _, _, delivery = _core()
    policy, capability = _policy_and_capability(request)
    issued_at = int(time.time())
    approval_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    captured: dict[str, Any] = {}

    def hold(prompt: dict[str, Any]) -> bool:
        captured.update(prompt)
        return False

    try:
        authority.approve_and_attest(
            request,
            context,
            audience=state["brain_id"],
            delivery_policy=policy,
            safe_label=f"Vault resource {request['resource']}",
            capability=capability,
            approve=hold,
            approval_id=approval_id,
            request_id=request_id,
            now=issued_at,
            ttl_seconds=PENDING_TTL,
        )
    except Exception as error:
        if getattr(error, "code", "") != "APPROVAL_DENIED" or not captured:
            raise
    pending = PendingApproval(
        approval_id=approval_id,
        request_id=request_id,
        request=dict(request),
        prompt=dict(captured),
        issued_at=issued_at,
        expires_at=issued_at + PENDING_TTL,
        stable_destination=candidate.stable_destination(),
        key_id=authority.key_id,
        brain_id=state["brain_id"],
        agent_id=state["agent_id"],
        delivery_policy=policy,
        capability=capability,
    )
    with _PENDING_LOCK:
        now = int(time.time())
        for key in [key for key, value in _PENDING.items() if value.expires_at < now]:
            _PENDING.pop(key, None)
        if len(_PENDING) >= MAX_PENDING:
            oldest = min(_PENDING, key=lambda key: _PENDING[key].issued_at)
            _PENDING.pop(oldest, None)
        _PENDING[approval_id] = pending
    try:
        _send_approval_ui(candidate, captured)
    except Exception:
        with _PENDING_LOCK:
            _PENDING.pop(approval_id, None)
        raise
    return json.dumps({
        "ok": False,
        "status": "approval_required",
        "approval_id": approval_id,
        "expires_at": captured["expires_at"],
        "message": "The trusted Hermes adapter sent the exact one-time approval UI directly to the owner DM.",
    }, ensure_ascii=True, sort_keys=True)


def _tool_handler(args: dict[str, Any], **kwargs: Any) -> str:
    try:
        authority, state = _snapshot()
        _, _, delivery = _core()
        request = delivery.validate_model_request(args)
        if request["action"] in {"locate", "metadata"}:
            return _metadata(request, state)
        context, candidate = _host_context(kwargs, state["agent_id"])
        if authority.key_id != state.get("active_key_id"):
            raise RuntimeError("The unlocked Hermes harness key is stale.")
        return _queue_approval(request, context, candidate)
    except Exception as error:
        code = getattr(error, "code", None) or "PRIVATE_DELIVERY_DENIED"
        return json.dumps({"ok": False, "error": code}, ensure_ascii=True, sort_keys=True)


class HermesPrivateAdapter:
    adapter_id = "hermes.private-dm"
    host = "local"
    operation = "deliver"

    def __init__(self, candidate: TurnCandidate):
        self.candidate = candidate

    async def _send(self, fields: Mapping[str, Any]) -> Mapping[str, Any]:
        adapter = self.candidate.gateway._adapter_for_source(self.candidate.source)
        if adapter is None:
            raise RuntimeError("The trusted Hermes destination adapter is unavailable.")
        lines = [f"{name}: {value if isinstance(value, str) else json.dumps(value, ensure_ascii=True)}" for name, value in fields.items()]
        message = "MegaBrain private delivery\n" + "\n".join(lines)
        metadata_fn = getattr(self.candidate.gateway, "_thread_metadata_for_source", None)
        metadata = metadata_fn(self.candidate.source) if callable(metadata_fn) else None
        result = await adapter.send(self.candidate.chat_id, message, metadata=metadata)
        if getattr(result, "success", True) is not True:
            raise RuntimeError("The trusted Hermes destination adapter rejected delivery.")
        return {"platform": self.candidate.platform, "delivered": True}

    def deliver(self, fields: Mapping[str, Any], *, timeout_seconds: int | None = None) -> Mapping[str, Any]:
        timeout = timeout_seconds or 15
        future = asyncio.run_coroutine_threadsafe(self._send(fields), self.candidate.loop)
        try:
            return future.result(timeout=max(1, min(timeout, 30)))
        except Exception:
            future.cancel()
            raise


async def _approval_ui(candidate: TurnCandidate, prompt: Mapping[str, Any]) -> None:
    adapter = candidate.gateway._adapter_for_source(candidate.source)
    if adapter is None:
        raise RuntimeError("The trusted Hermes approval adapter is unavailable.")
    message = "\n".join((
        "MegaBrain exact one-time approval",
        f"Resource: {prompt['safe_label']}",
        f"Fields: {', '.join(prompt['fields'])}",
        f"Purpose: {prompt['purpose']}",
        f"Requester: {prompt['requester']}",
        f"Destination: {prompt['destination']}",
        f"Expires at: {prompt['expires_at']}",
        str(prompt["warning"]),
        f"Approve exactly this request: /megabrain-approve {prompt['approval_id']}",
    ))
    metadata_fn = getattr(candidate.gateway, "_thread_metadata_for_source", None)
    metadata = metadata_fn(candidate.source) if callable(metadata_fn) else None
    result = await adapter.send(candidate.chat_id, message, metadata=metadata)
    if getattr(result, "success", True) is not True:
        raise RuntimeError("The trusted Hermes approval adapter rejected the prompt.")


def _send_approval_ui(candidate: TurnCandidate, prompt: Mapping[str, Any]) -> None:
    future = asyncio.run_coroutine_threadsafe(_approval_ui(candidate, prompt), candidate.loop)
    try:
        future.result(timeout=15)
    except Exception:
        future.cancel()
        raise


def _complete_pending(pending: PendingApproval, context: Any, candidate: TurnCandidate) -> dict[str, Any]:
    authority, state = _snapshot()
    _, _, delivery = _core()
    if authority.key_id != pending.key_id or state.get("brain_id") != pending.brain_id:
        raise RuntimeError("The exact approval belongs to another harness key or Vault audience.")
    envelope, _ = authority.approve_and_attest(
        pending.request,
        context,
        audience=pending.brain_id,
        delivery_policy=pending.delivery_policy,
        safe_label=pending.prompt["safe_label"],
        capability=pending.capability,
        approve=lambda prompt: prompt.get("approval_id") == pending.approval_id,
        approval_id=pending.approval_id,
        request_id=pending.request_id,
        now=pending.issued_at,
        ttl_seconds=PENDING_TTL,
    )
    store, _ = _vault_store(Path(state["brain_root"]))
    sealed = delivery.request_attested_release(store, pending.request, envelope)
    adapter = (
        delivery.SyntheticTokenCheckAdapter()
        if pending.request["action"] == "use"
        else HermesPrivateAdapter(candidate)
    )
    return delivery.open_and_deliver(authority, sealed, envelope, adapter)


async def _approve_command(raw_args: str) -> str:
    approval_id = raw_args.strip()
    try:
        uuid.UUID(approval_id)
        candidate = _TURN.get()
        if candidate is None:
            raise RuntimeError("PRIVATE_CONTEXT_UNATTESTED")
        with _PENDING_LOCK:
            pending = _PENDING.get(approval_id)
        if pending is None or pending.expires_at < int(time.time()):
            with _PENDING_LOCK:
                _PENDING.pop(approval_id, None)
            raise RuntimeError("APPROVAL_EXPIRED")
        if candidate.stable_destination() != pending.stable_destination:
            raise RuntimeError("DESTINATION_NOT_PAIRED")
        with _PENDING_LOCK:
            pending = _PENDING.pop(approval_id, None)
        if pending is None:
            raise RuntimeError("APPROVAL_REPLAYED")
        context = _command_context(candidate, pending.agent_id)
        receipt = await asyncio.to_thread(_complete_pending, pending, context, candidate)
        if receipt.get("delivered") is not True:
            raise RuntimeError("PRIVATE_DELIVERY_DENIED")
        return f"MegaBrain {receipt.get('action', 'delivery')} completed for this exact approval."
    except Exception as error:
        safe_runtime_codes = {
            "PRIVATE_CONTEXT_UNATTESTED",
            "APPROVAL_EXPIRED",
            "APPROVAL_REPLAYED",
            "DESTINATION_NOT_PAIRED",
            "PRIVATE_DELIVERY_DENIED",
        }
        runtime_code = str(error)
        code = getattr(error, "code", None) or (
            runtime_code if runtime_code in safe_runtime_codes else "PRIVATE_DELIVERY_DENIED"
        )
        return f"MegaBrain private delivery denied: {code}."


def _status_command(_: str) -> str:
    paired = _state_path().is_file()
    with _STATE_LOCK:
        unlocked = _AUTHORITY is not None
    provenance = False
    try:
        from gateway.session_context import _VAR_MAP, get_session_env
        provenance = (
            {"HERMES_SESSION_SOURCE", "HERMES_SESSION_CHAT_TYPE"} <= set(_VAR_MAP)
            and get_session_env("HERMES_SESSION_SOURCE", "") in {
                "gateway_user", "gateway_internal", "gateway_unknown"
            }
            and get_session_env("HERMES_SESSION_CHAT_TYPE", "") != ""
        )
    except Exception:
        pass
    return f"MegaBrain harness: paired={str(paired).lower()} unlocked={str(unlocked).lower()} provenance={str(provenance).lower()}."


def _peer_is_owner(connection: socket.socket) -> bool:
    if hasattr(connection, "getpeereid"):
        uid, _ = connection.getpeereid()
        return uid == os.getuid()
    if hasattr(socket, "SO_PEERCRED"):
        credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        _, uid, _ = struct.unpack("3i", credentials)
        return uid == os.getuid()
    if hasattr(socket, "LOCAL_PEERCRED"):
        credentials = connection.getsockopt(0, socket.LOCAL_PEERCRED, 8)
        _, uid = struct.unpack("=II", credentials)
        return uid == os.getuid()
    return False


class ControlServer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._failures: deque[float] = deque(maxlen=16)

    def ensure_started(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._serve, name="megabrain-harness-control", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._stop.set()
        if thread is not None:
            thread.join(timeout=2)
        try:
            _control_path().unlink(missing_ok=True)
        except Exception:
            pass
        with self._lock:
            if self._thread is thread:
                self._thread = None

    def _serve(self) -> None:
        server: socket.socket | None = None
        try:
            path = _control_path()
            if path.exists() or path.is_symlink():
                path.unlink()
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(path))
            os.chmod(path, 0o600)
            server.listen(4)
            server.settimeout(1)
        except Exception:
            if server is not None:
                server.close()
            return
        with server:
            while not self._stop.is_set():
                try:
                    connection, _ = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                with connection:
                    response = self._handle(connection)
                    try:
                        connection.sendall(json.dumps(response, sort_keys=True).encode("utf-8") + b"\n")
                    except OSError:
                        pass
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def _handle(self, connection: socket.socket) -> dict[str, Any]:
        if not _peer_is_owner(connection):
            return {"ok": False, "error": "OWNER_LOCAL_CONTROL_REQUIRED"}
        connection.settimeout(5)
        data = bytearray()
        try:
            while not data.endswith(b"\n") and len(data) <= 65536:
                part = connection.recv(4096)
                if not part:
                    break
                data.extend(part)
            request = json.loads(data)
        except Exception:
            return {"ok": False, "error": "CONTROL_REQUEST_INVALID"}
        if not isinstance(request, dict) or request.get("schema") != CONTROL_SCHEMA:
            return {"ok": False, "error": "CONTROL_REQUEST_INVALID"}
        action = request.get("action")
        if action == "status" and set(request) == {"schema", "action"}:
            with _STATE_LOCK:
                return {"ok": True, "unlocked": _AUTHORITY is not None, "paired": _state_path().is_file()}
        if action == "lock" and set(request) == {"schema", "action"}:
            _lock_memory()
            return {"ok": True, "locked": True}
        if action != "unlock" or set(request) != {"schema", "action", "passphrase"}:
            return {"ok": False, "error": "CONTROL_REQUEST_INVALID"}
        now = time.monotonic()
        while self._failures and now - self._failures[0] > 60:
            self._failures.popleft()
        if len(self._failures) >= 5:
            return {"ok": False, "error": "UNLOCK_RATE_LIMITED"}
        passphrase = request.get("passphrase")
        if not isinstance(passphrase, str):
            return {"ok": False, "error": "HARNESS_PASSPHRASE_REQUIRED"}
        try:
            inner = _decrypt_state(passphrase)
            authority = _active_authority(inner)
            _set_unlocked(inner, authority)
            inner.clear()
            self._failures.clear()
            return {"ok": True, "unlocked": True, "key_id": authority.key_id}
        except Exception:
            self._failures.append(now)
            return {"ok": False, "error": "HARNESS_UNLOCK_FAILED"}
        finally:
            request["passphrase"] = ""
            passphrase = ""
            data.clear()


_CONTROL = ControlServer()


def _control_request(action: str, passphrase: str | None = None) -> dict[str, Any]:
    request: dict[str, Any] = {"schema": CONTROL_SCHEMA, "action": action}
    if passphrase is not None:
        request["passphrase"] = passphrase
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(5)
    data = bytearray()
    try:
        connection.connect(str(_control_path()))
        connection.sendall(json.dumps(request, sort_keys=True).encode("utf-8") + b"\n")
        while not data.endswith(b"\n") and len(data) <= 65536:
            part = connection.recv(4096)
            if not part:
                break
            data.extend(part)
        response = json.loads(data)
        return response if isinstance(response, dict) else {"ok": False, "error": "CONTROL_RESPONSE_INVALID"}
    finally:
        request.clear()
        data.clear()
        connection.close()


def _require_tty() -> None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError("Open this command in an owner-local interactive terminal.")


def _prompt_new_harness_passphrase() -> str:
    first = getpass.getpass("Harness passphrase: ")
    second = getpass.getpass("Confirm harness passphrase: ")
    if first != second or len(first) < 12:
        raise RuntimeError("Harness passphrases must match and contain at least 12 characters.")
    return first


def _destination_from_args(_args: argparse.Namespace) -> dict[str, str]:
    platform = input("Owner DM platform: ").strip()
    user_id = input("Exact owner user ID: ").strip()
    chat_id = input("Exact owner DM chat ID: ").strip()
    thread_id = input("Exact thread ID (blank for none): ").strip()
    if not platform or not user_id or not chat_id:
        raise RuntimeError("Platform, owner user ID, and owner DM chat ID are required.")
    if platform.lower() in {"email", "api", "api_server", "webhook", "cron", "local"}:
        raise RuntimeError("The selected platform is not eligible for paired DM delivery.")
    if any(len(value) > 512 or any(ord(character) < 32 for character in value) for value in (
        platform, user_id, chat_id, thread_id
    )):
        raise RuntimeError("One or more paired destination identifiers are invalid.")
    return {
        "platform": platform,
        "chat_type": "dm",
        "user_id": user_id,
        "chat_id": chat_id,
        "thread_id": thread_id,
        "kind": "private_dm",
    }


def _pair(args: argparse.Namespace) -> None:
    _require_tty()
    if _state_path().exists():
        raise RuntimeError("Harness state already exists; rotate or revoke it explicitly.")
    _, vault, delivery = _core()
    brain_root = Path(args.brain_root).expanduser().resolve()
    store, brain_id = _vault_store(brain_root)
    vault_passphrase = getpass.getpass("Vault passphrase: ")
    harness_passphrase = _prompt_new_harness_passphrase()
    authority = delivery.HarnessAuthority.generate()
    destination = _destination_from_args(args)
    master_key = store.unlock(passphrase=vault_passphrase)
    result = delivery.pair_harness(store, master_key, authority, [destination])
    inner = {
        "brain_root": str(brain_root),
        "brain_id": brain_id,
        "agent_id": _agent_id(brain_root),
        "active_key_id": authority.key_id,
        "authorities": [_authority_record(authority, vault)],
        "destinations": [destination],
        "created_at": int(time.time()),
    }
    try:
        _save_state(inner, harness_passphrase)
    except Exception:
        delivery.revoke_harness_key(store, authority.issuer_instance, authority.key_id)
        raise
    print(json.dumps({"ok": True, "paired": True, "issuer_instance": result["issuer_instance"], "key_id": result["key_id"], "fingerprint": result["fingerprint"]}, sort_keys=True))


def _rotate(args: argparse.Namespace) -> None:
    _require_tty()
    _, vault, delivery = _core()
    old_passphrase = getpass.getpass("Current harness passphrase: ")
    inner = _decrypt_state(old_passphrase)
    current = _active_authority(inner)
    new_passphrase = _prompt_new_harness_passphrase()
    vault_passphrase = getpass.getpass("Vault passphrase: ")
    store, _ = _vault_store(Path(inner["brain_root"]))
    replacement = delivery.HarnessAuthority.generate(current.issuer_instance)
    master_key = store.unlock(passphrase=vault_passphrase)
    result = delivery.rotate_harness_key(
        store,
        master_key,
        current.key_id,
        replacement,
        inner["destinations"],
        grace_seconds=args.grace_seconds,
    )
    inner["authorities"].append(_authority_record(replacement, vault))
    inner["active_key_id"] = replacement.key_id
    try:
        _save_state(inner, new_passphrase)
    except Exception:
        delivery.rollback_harness_key(
            store,
            current.issuer_instance,
            current.key_id,
            replacement.key_id,
        )
        raise
    _lock_memory()
    print(json.dumps({"ok": True, "rotated": True, "key_id": result["key_id"], "previous_key_id": result["previous_key_id"], "grace_until": result["grace_until"]}, sort_keys=True))


def _rollback(args: argparse.Namespace) -> None:
    _require_tty()
    _, _, delivery = _core()
    harness_passphrase = getpass.getpass("Harness passphrase: ")
    inner = _decrypt_state(harness_passphrase)
    known_keys = {
        record.get("key_id")
        for record in inner.get("authorities", [])
        if isinstance(record, Mapping)
    }
    if args.restore_key_id not in known_keys or args.revoke_key_id not in known_keys:
        raise RuntimeError("Rollback requires two keys from the encrypted harness keyring.")
    vault_passphrase = getpass.getpass("Vault passphrase: ")
    store, _ = _vault_store(Path(inner["brain_root"]))
    store.unlock(passphrase=vault_passphrase)
    result = delivery.rollback_harness_key(store, args.issuer_instance, args.restore_key_id, args.revoke_key_id)
    inner["active_key_id"] = args.restore_key_id
    _save_state(inner, harness_passphrase)
    _lock_memory()
    print(json.dumps(result, sort_keys=True))


def _revoke(args: argparse.Namespace) -> None:
    _require_tty()
    _, _, delivery = _core()
    harness_passphrase = getpass.getpass("Harness passphrase: ")
    inner = _decrypt_state(harness_passphrase)
    vault_passphrase = getpass.getpass("Vault passphrase: ")
    store, _ = _vault_store(Path(inner["brain_root"]))
    store.unlock(passphrase=vault_passphrase)
    result = delivery.revoke_harness_key(store, args.issuer_instance, args.key_id)
    if inner.get("active_key_id") == args.key_id:
        _state_path().unlink()
    else:
        _save_state(inner, harness_passphrase)
    _lock_memory()
    print(json.dumps(result, sort_keys=True))


def _cli(args: argparse.Namespace) -> None:
    action = args.megabrain_vault_action
    if action == "pair":
        _pair(args)
        return
    if action == "rotate":
        _rotate(args)
        return
    if action == "rollback":
        _rollback(args)
        return
    if action == "revoke":
        _revoke(args)
        return
    if action == "unlock":
        _require_tty()
        response = _control_request("unlock", getpass.getpass("Harness passphrase: "))
    else:
        response = _control_request(action)
    print(json.dumps(response, sort_keys=True))


def _setup_cli(parser: argparse.ArgumentParser) -> None:
    subcommands = parser.add_subparsers(dest="megabrain_vault_action", required=True)
    pair = subcommands.add_parser("pair", help="Pair an exact owner DM and encrypted harness key")
    pair.add_argument("--brain-root", default=str(Path.home() / ".megabrain" / "clones" / "hermes"))
    rotate = subcommands.add_parser("rotate", help="Rotate the harness key")
    rotate.add_argument("--grace-seconds", type=int, default=300)
    rollback = subcommands.add_parser("rollback", help="Rollback during the key grace window")
    rollback.add_argument("--issuer-instance", required=True)
    rollback.add_argument("--restore-key-id", required=True)
    rollback.add_argument("--revoke-key-id", required=True)
    revoke = subcommands.add_parser("revoke", help="Revoke one harness key")
    revoke.add_argument("--issuer-instance", required=True)
    revoke.add_argument("--key-id", required=True)
    subcommands.add_parser("unlock", help="Unlock the gateway harness key from a no-echo TTY")
    subcommands.add_parser("lock", help="Discard the gateway harness key from memory")
    subcommands.add_parser("status", help="Show safe pairing and lock status")
    parser.set_defaults(func=_cli)


def register(ctx: Any, schema: dict[str, Any]) -> None:
    ctx.register_tool(
        name="megabrain_vault",
        toolset="megabrain-vault",
        schema=schema,
        handler=_tool_handler,
        check_fn=_tool_available,
        description="Owner-approved attested MegaBrain Vault delivery",
        emoji="🔐",
    )
    ctx.register_hook("pre_gateway_dispatch", _capture_turn)
    ctx.register_command(
        "megabrain-approve",
        _approve_command,
        description="Approve one exact pending MegaBrain Vault request",
        args_hint="<approval-id>",
    )
    ctx.register_command(
        "megabrain-vault-status",
        _status_command,
        description="Show safe MegaBrain harness status",
    )
    ctx.register_cli_command(
        name="megabrain-vault",
        help="Pair, unlock, rotate, and revoke the MegaBrain Vault harness",
        setup_fn=_setup_cli,
        handler_fn=_cli,
    )
