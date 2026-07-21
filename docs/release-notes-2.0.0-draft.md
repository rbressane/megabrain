# MegaBrain 2.0.0 Draft Release Notes

This local draft separates bounded retrieval from the unreleased Vault stack and adds the protocol-2 canonical resource, archive, import, access-policy, and derived-cache model.

It preserves protocol-1 memory IDs and requires an explicit owner-local migration. New resources use stable URIs and immutable revisions; imports are fingerprint-bound and review-first; private/sensitive reads default deny; indexes rebuild from committed Git state; general always-on caches are deterministic and non-authoritative.

The built-in private local browser now reports generation-scoped synchronization, snapshot time, newest-memory freshness, inclusion verification, pending local commit state, and safe stale reasons. Setup teaches `Synchronize and open my MegaBrain` as the single synchronized validation and regeneration action; `Open my MegaBrain` remains equivalent.

Sensitive synchronized bodies and attachments remain unavailable. This draft does not merge, release, deploy, migrate real sources, enable consumers, change Hermes memory configuration, or retire any legacy store. User-zero cutover and high-assurance security language require the approval gates in the review bundle and independent review where stated.
