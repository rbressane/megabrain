# MegaBrain

This private repository is your local-first Markdown brain. Connected agents synchronize it through Git and store durable knowledge as immutable files under `brain/`.

Normal use happens through conversation. Ask a connected agent to remember, inspect, update, or open MegaBrain. The independently installed MegaBrain runtime performs those operations; this repository contains personal brain data, not executable product code.

The repository intentionally begins with zero personal memories. Never store passwords, identity numbers, tokens, private keys, recovery codes, cookies, raw connection strings, or sensitive document contents here.

MegaBrain Vault is separate local encrypted storage under `~/.megabrain/vaults/<brain-id>/`; it is never synchronized through this repository. Brain may store safe facts such as a document's expiry date and a logical `megabrain-vault://...` resource pointer, but never the protected value. Agents can inspect safe status and masked metadata; setup, backup, recovery, administration, and protected values stay in the local owner control plane.

Owner-local encrypted storage and agent-safe masked metadata remain the default. Plaintext delivery is available only through a reviewed owner-paired harness with exact task-local destination proof and a fresh one-shot approval. Agents must never ask for protected values in chat or supply destination, approval, private-context, signature, or attestation fields themselves.
