# MegaBrain 1.2.0 Draft Release Notes

Version 1.2.0 remains unreleased. These notes describe a stacked private-delivery epic and do not authorize merge, tagging, deployment, stable installation, or consumer testing.

The 1.1 containment boundary remains the default. When an owner explicitly pairs a reviewed trusted harness, MegaBrain can validate short-lived destination attestations, capture exact one-shot approval, enforce per-resource policy, and sealed-box selected fields to a trusted adapter. The model sees only the four safe request fields and a value-free receipt.

Vault schema 2 adds transactional harness pairing/rotation/revocation, exact keyed destination bindings, resource policies, bounded direct-use capabilities, replay state, and value-free delivery audits. Schema 1 migrates on first open; downgrade is unsupported. Credentials default to direct use, recovery remains local, identity/health/finance remain local unless the owner opts one resource into an exact paired DM, and every group/channel/email/API/webhook/cron/delegated/unattended/background/internal context is denied.

The reference direct-use adapter is synthetic and no-network. No real provider, remote broker, hosted relay, TCP/HTTP Vault endpoint, arbitrary shell, or secret-bearing model response is added.

The separately reviewable Hermes plugin encrypts its harness private state at rest, unlocks it into the gateway process only through an owner-local no-echo Unix-socket control, fails closed without host-bound user/internal and chat-type provenance, and renders the exact approval UI directly to the owner DM. The owner slash command—not a second model call—signs and completes the pending release. The generic product-neutral Hermes provenance seam is tracked separately upstream.

Before any release, the stacked MegaBrain and harness-integration drafts require maintainer review, full platform CI, explicit merge and release decisions, and independent security review for any high-assurance claim.
