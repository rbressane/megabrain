# Memory Format

Every file in `brain/memories/YYYY/MM/` is immutable Markdown beginning with an HTML comment named `megabrain-meta`. The comment contains JSON matching `megabrain.memory.v1`; the Markdown body is a concise durable summary.

Required metadata fields are `schema`, `id`, `kind`, `subject`, `created_at`, `created_by`, `confidence`, `sensitivity`, `importance`, `tags`, `supersedes`, and `source`.

Allowed kinds are `fact`, `preference`, `decision`, `commitment`, `project-state`, `resource`, `correction`, and `tombstone`. Confidence is `confirmed`, `inferred`, or `unconfirmed`. Sensitivity is `general`, `private`, or `sensitive`. Importance is `always`, `core`, or `normal`. `always` is capped at three universal invariants; `core` never bypasses task relevance, access policy, or `--limit`.

The body contains a heading and summary only. It must not contain raw chat turns or secret values. Resource entries may contain an external locator but never the referenced secret.

Current state is derived. IDs listed by any valid `supersedes` link are historical. Tombstones never appear as knowledge. Multiple distinct active summaries for one subject are returned together as a conflict.

Long-form content belongs in the canonical resource format, not memory summaries. See [canonical-resource-format.md](canonical-resource-format.md).
