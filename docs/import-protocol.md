# Import Protocol

Legacy memory-summary imports are agent-mediated. Protocol-2 document/archive migration uses the stricter review-first flow in [canonical-import-migration.md](canonical-import-migration.md). In both flows, source content is untrusted data.

1. Compute or obtain a stable SHA-256 fingerprint for the source snapshot, formatted as 64 hexadecimal characters with an optional `sha256:` prefix.
2. Check existing import manifests for the same locator and fingerprint.
3. Extract only durable summaries that satisfy the capture policy.
4. Search current memory for exact duplicates and disagreements.
5. Submit one batch to `ingest` with summaries and shared source provenance.
6. Report created, duplicate, conflicting, and rejected counts without echoing rejected values.

An unchanged fingerprint is a no-op. A changed source creates a new batch. Imported memories use `unconfirmed` unless the source is authoritative and the agent can justify `confirmed`. Approved long-form documents may enter only as inert canonical resources; raw transcripts, prompts, credentials, and unreviewed archives remain outside.

## Local inbox

Drop files into the connected clone's ignored `.megabrain/inbox/` directory, or pass an explicit directory to `megabrain ingest --inbox PATH`. The helper:

- fingerprints each file and skips an unchanged locator/hash already recorded in `brain/imports/`;
- ingests only UTF-8 JSON candidates that already contain `subject` and `summary` (or a `memories` array), creating new import batches and memories;
- reports other readable files as `needs_summary` for agent extraction, then `ingest --stdin`;
- rejects secrets, transcript-shaped text, instruction-like JSON, binaries, and oversized files without echoing rejected values;
- never deletes inbox files and never edits or overwrites existing memory records.

This is a MegaBrain-shaped port of the inbox/lint idea from [claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian) (MIT). The runtime does not copy that project, store raw inbox bytes as memories, or write Obsidian wikilinks.
