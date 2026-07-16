#!/usr/bin/env python3
"""Human-only local TTY control plane for MegaBrain Vault.

This entry point deliberately has no JSON/stdin automation mode. Secret input uses
no-echo terminal prompts and owner-only actions never pass through the model-facing
MegaBrain command surface.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path
from typing import Any, Protocol

import megabrain
import vault


class Terminal(Protocol):
    def ask(self, prompt: str) -> str: ...
    def secret(self, prompt: str) -> str: ...
    def show(self, message: str) -> None: ...


class LocalTerminal:
    @classmethod
    def require(cls) -> "LocalTerminal":
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise vault.VaultError(
                "LOCAL_ACTION_REQUIRED",
                "Open the MegaBrain Vault owner control plane in a local interactive terminal.",
            )
        return cls()

    def ask(self, prompt: str) -> str:
        return input(prompt)

    def secret(self, prompt: str) -> str:
        return getpass.getpass(prompt)

    def show(self, message: str) -> None:
        print(message, flush=True)


def required(terminal: Terminal, prompt: str) -> str:
    value = terminal.ask(prompt).strip()
    if not value:
        raise vault.VaultError("LOCAL_INPUT_REQUIRED", "The local owner action is missing required input.")
    return value


def passphrase(terminal: Terminal, *, confirm: bool = False) -> str:
    value = terminal.secret("Vault passphrase: ")
    if confirm and value != terminal.secret("Confirm Vault passphrase: "):
        raise vault.VaultError("PASSPHRASE_MISMATCH", "The local passphrase confirmation did not match.")
    return value


def safe_receipt(action: str, result: dict[str, Any], terminal: Terminal) -> None:
    details = []
    for key in (
        "ready", "created", "unlocked", "locked", "rotated", "deleted", "restored",
        "revoked", "policy", "capability_id", "recovery_file", "path",
    ):
        if key in result:
            details.append(f"{key}={result[key]}")
    suffix = f" ({', '.join(details)})" if details else ""
    terminal.show(f"MegaBrain Vault: {action} complete{suffix}.")


def local_payload(action: str, terminal: Terminal) -> dict[str, Any]:
    if action == "setup":
        return {
            "passphrase": passphrase(terminal, confirm=True),
            "recovery_path": required(terminal, "New recovery file path: "),
        }
    if action == "confirm":
        return {"confirm_recovery_saved": True}
    if action == "unlock":
        timeout = required(terminal, "Idle timeout seconds (5-3600): ")
        try:
            parsed_timeout = int(timeout)
        except ValueError as error:
            raise vault.VaultError("INVALID_TIMEOUT", "The local idle timeout must be an integer.") from error
        return {"passphrase": passphrase(terminal), "idle_timeout": parsed_timeout}
    if action == "put":
        logical_id = required(terminal, "Logical resource ID: ")
        item_type = required(terminal, "Item type: ")
        if item_type not in vault.ITEM_TYPE_FIELDS:
            raise vault.VaultError("INVALID_ITEM", "The selected local item type is unsupported.")
        label = required(terminal, "Safe local label: ")
        field_names = [name.strip() for name in required(terminal, "Field names (comma separated): ").split(",")]
        if not set(field_names) <= vault.ITEM_TYPE_FIELDS[item_type]:
            raise vault.VaultError("INVALID_ITEM_SCHEMA", "One or more local field names are unsupported.")
        fields = {name: terminal.secret(f"Protected value for {name}: ") for name in field_names}
        return {
            "passphrase": passphrase(terminal),
            "item": {"logical_id": logical_id, "type": item_type, "label": label, "fields": fields},
        }
    if action == "reveal":
        return {
            "passphrase": passphrase(terminal),
            "resource": required(terminal, "Logical resource ID: "),
            "fields": [name.strip() for name in required(terminal, "Selected fields (comma separated): ").split(",")],
            "purpose": required(terminal, "Purpose code: "),
        }
    if action == "attach":
        operation = required(terminal, "Attachment operation (add/get): ").lower()
        payload: dict[str, Any] = {"passphrase": passphrase(terminal), "operation": operation}
        if operation == "add":
            payload.update(
                {
                    "resource": required(terminal, "Logical resource ID: "),
                    "source": required(terminal, "Local source file: "),
                    "filename": required(terminal, "Safe filename: "),
                    "mime_type": required(terminal, "MIME type: "),
                }
            )
        elif operation == "get":
            payload.update(
                {
                    "attachment_id": required(terminal, "Attachment ID: "),
                    "destination": required(terminal, "New local destination file: "),
                }
            )
        else:
            raise vault.VaultError("INVALID_ATTACHMENT_OPERATION", "Choose add or get in the local control plane.")
        return payload
    if action == "export":
        return {"passphrase": passphrase(terminal), "destination": required(terminal, "New backup destination: ")}
    if action == "restore":
        material = required(terminal, "Unlock with passphrase or recovery key (passphrase/recovery): ").lower()
        payload = {"source": required(terminal, "Backup source: ")}
        if material == "passphrase":
            payload["passphrase"] = passphrase(terminal)
        elif material == "recovery":
            payload["recovery_key"] = terminal.secret("Recovery key: ")
        else:
            raise vault.VaultError("UNLOCK_MATERIAL_REQUIRED", "Choose passphrase or recovery in the local control plane.")
        return payload
    if action == "grant":
        return {
            "passphrase": passphrase(terminal),
            "agent_id": required(terminal, "Agent ID: "),
            "scopes": [value.strip() for value in required(terminal, "Scopes (comma separated): ").split(",")],
            "resource_classes": [
                value.strip() for value in required(terminal, "Resource classes (comma separated): ").split(",")
            ],
        }
    if action == "revoke":
        return {"passphrase": passphrase(terminal), "agent_id": required(terminal, "Agent ID: ")}
    if action == "rotate-passphrase":
        old = passphrase(terminal)
        new = terminal.secret("New Vault passphrase: ")
        if new != terminal.secret("Confirm new Vault passphrase: "):
            raise vault.VaultError("PASSPHRASE_MISMATCH", "The local passphrase confirmation did not match.")
        return {"passphrase": old, "new_passphrase": new}
    if action == "rotate-recovery":
        return {
            "passphrase": passphrase(terminal),
            "recovery_path": required(terminal, "New recovery file path: "),
        }
    if action == "delete":
        resource = required(terminal, "Logical resource ID: ")
        if required(terminal, "Type DELETE to destroy the active key: ") != "DELETE":
            raise vault.VaultError("OWNER_CONFIRMATION_REQUIRED", "Local deletion was not confirmed.")
        return {"passphrase": passphrase(terminal), "resource": resource}
    if action == "audit":
        return {"passphrase": passphrase(terminal), "limit": 100}
    if action == "delivery-policy":
        return {
            "passphrase": passphrase(terminal),
            "resource": required(terminal, "Logical resource ID: "),
            "policy": required(
                terminal,
                "Policy (metadata_only/local_secure_ui/private_dm_opt_in/direct_use_only/never_reveal): ",
            ),
        }
    if action == "grant-direct-use":
        timeout = required(terminal, "Timeout seconds (1-30): ")
        try:
            parsed_timeout = int(timeout)
        except ValueError as error:
            raise vault.VaultError("CAPABILITY_TIMEOUT_INVALID", "The direct-use timeout must be an integer.") from error
        return {
            "passphrase": passphrase(terminal),
            "resource": required(terminal, "Credential resource ID: "),
            "capability_id": required(terminal, "Capability ID: "),
            "adapter_id": required(terminal, "Trusted adapter ID: "),
            "host": required(terminal, "Exact allowed host: "),
            "operation": required(terminal, "Exact allowed operation: "),
            "fields": [name.strip() for name in required(terminal, "Exact fields (comma separated): ").split(",")],
            "timeout_seconds": parsed_timeout,
        }
    if action == "revoke-direct-use":
        return {
            "passphrase": passphrase(terminal),
            "resource": required(terminal, "Credential resource ID: "),
            "capability_id": required(terminal, "Capability ID: "),
        }
    if action == "revoke-harness":
        return {
            "passphrase": passphrase(terminal),
            "issuer_instance": required(terminal, "Harness issuer instance: "),
            "key_id": required(terminal, "Harness key ID: "),
        }
    if action == "delivery-audit":
        return {"passphrase": passphrase(terminal), "limit": 100}
    return {}


def run_local_action(root: Path, action: str, terminal: Terminal) -> dict[str, Any]:
    command_action = "setup" if action == "confirm" else action
    payload = local_payload(action, terminal)
    result = megabrain.command_vault(root, command_action, payload, trusted_local=True)
    if action == "reveal":
        for name, value in result["fields"].items():
            terminal.show(f"{name}: {value}")
    elif action in {"audit", "delivery-audit"}:
        terminal.show(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    else:
        safe_receipt(action, result, terminal)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="megabrain-vault-local", description="Human-only local MegaBrain Vault control plane")
    parser.add_argument(
        "action",
        choices=(
            "setup", "confirm", "status", "unlock", "lock", "put", "reveal", "attach", "export",
            "restore", "grant", "revoke", "rotate-passphrase", "rotate-recovery", "delete", "audit", "doctor",
            "delivery-policy", "grant-direct-use", "revoke-direct-use", "revoke-harness", "delivery-audit",
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        terminal = LocalTerminal.require()
        run_local_action(megabrain.repo_root(), args.action, terminal)
        return 0
    except vault.VaultError as error:
        try:
            LocalTerminal.require().show(f"MegaBrain Vault: {error.code}: {error.message}")
        except vault.VaultError:
            pass
        return 2
    except megabrain.BrainError as error:
        try:
            LocalTerminal.require().show(f"MegaBrain Vault: {error.code}: {error.message}")
        except vault.VaultError:
            pass
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
