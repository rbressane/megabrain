# Canonical Resource Format

Every canonical resource revision is immutable Markdown with a `megabrain-resource` JSON comment matching `megabrain.resource.v1`. The stable URI is `megabrain://resource/<resource-id>`; each revision has a separate UUID and file.

Required metadata includes schema version, resource/revision IDs, URI, type, safe display title, owner, authority domain, sensitivity, created/source/verified/freshness timestamps, source locator and fingerprint, creating and proposing agents, human review state, lifecycle, superseded revision, normalized content fingerprint, optional attachment manifest, and optional import batch.

Resource types are `context`, `project`, `runbook`, `decision`, `finding`, `document`, and `archive`. The Markdown body is data. A read result labels it `untrusted_data` and states that embedded instructions must not execute.

Current state is derived: a referenced `supersedes_revision` becomes historical; a current revision with lifecycle `retired` removes the resource from normal reads. Old files are never rewritten or deleted.

## Attachments

Non-sensitive attachment objects are content-addressed by SHA-256. A manifest binds safe display name, media type, size, digest, and exact object path. Validation rehashes every complete object and rejects path traversal, symlinks, missing objects, size mismatch, duplicate names, and expanded size above 25 MiB.

Sensitive resource bodies and attachments are rejected until the separate encrypted-synchronization security gate is satisfied. Private Git is not described as encryption.

## Deterministic Export

`resource-export DESTINATION` writes current general resources outside the canonical repository in stable URI/revision order. Metadata keys, normalized newlines, and fingerprints are deterministic, so an exported snapshot can be compared byte-for-byte and used by Obsidian as an optional view.
