# Product Feedback Loop

MegaBrain turns material user-zero discoveries into privacy-safe implementation proposals without telemetry or automatic publication. Private memories remain in the user's Brain; public product learning is reduced to a sanitized Product Bake Candidate.

## Lifecycle

```text
user-zero interaction
→ classify private memory vs reusable product learning
→ sanitize
→ render Product Bake Candidate
→ owner reviews and forwards
→ coding agent implements with synthetic tests
→ owner explicitly authorizes publication
→ stable release
→ consumer runs megabrain update
→ user-zero retests the stable runtime
→ candidate closes or is corrected
```

A local patch or draft PR is not product completion. The loop closes only after a stable release is installed and retested by a consumer.

## Trigger

Create a candidate for reusable public-product findings:

- a missing first-class command;
- repeated manual work or workaround;
- behavior that contradicts documentation;
- an installation, update, migration or recovery weakness;
- a retrieval, correction, privacy or security failure;
- a product-wide UX or policy decision;
- a user-zero result that should become an acceptance test;
- documentation that would have prevented confusion;
- a capability consistently needed across supported agents.

Do not create one for personal preferences or private facts, client-specific content, credentials or private infrastructure, transient progress, one-off local noise, incidents with no reusable lesson, or behavior already implemented and documented upstream. Silence is correct when no actionable product learning exists.

## Privacy Contract

Before rendering:

1. Separate the public product lesson from private user context.
2. Remove names, client identifiers, private repository paths, credentials, secrets, private URLs and raw records.
3. Replace sensitive examples with synthetic structural equivalents.
4. Keep only enough evidence to reproduce public product behavior without a private Brain.
5. Never upload, transmit, open an issue, create a branch or PR, merge, tag, or release automatically.

The renderer rejects transcript-shaped input, known secret patterns, private local paths, local-network URLs, unsupported categories and oversized source-dump-shaped input. Rejection messages never echo the rejected value. Pattern matching is defensive, not a substitute for agent judgment and owner review.

## Offline Renderer

Pass structured JSON on standard input:

```bash
megabrain feedback --stdin
```

Required scalar fields:

- `category`
- `title`
- `mission`
- `observation`
- `why_product`
- `current_behavior`
- `expected_behavior`
- `release_notes`

Required list fields:

- `reproduction`
- `scope`
- `acceptance_criteria`
- `tests`
- `documentation`
- `evidence`

`privacy_constraints` is an optional list. The renderer always adds the canonical no-private-Brain, synthetic-fixture, secret-safe and no-automatic-transmission constraints.

Supported categories are:

- `missing_command`
- `repeated_workaround`
- `behavior_documentation_mismatch`
- `install_update_migration_recovery`
- `retrieval_correction_privacy_security_failure`
- `product_ux_policy`
- `acceptance_test`
- `documentation_gap`
- `cross_agent_capability`

The command performs no network operation and writes the deterministic Markdown prompt to stdout. It writes a local file only when `--output PATH` explicitly names a new file in an existing directory. It refuses to overwrite a file.

The canonical template is [the shipped product asset](../skill/megabrain/assets/product-bake-candidate.md). Its sections cover mission, observation, product relevance, current and expected behavior, synthetic reproduction, scope, acceptance criteria, tests, documentation, privacy, migration, evidence and authorization.

## Agent Completion Behavior

When a material candidate exists, the shipped skill appends:

```text
Product bake candidate: MegaBrain
Reason: <one sentence>
I prepared a sanitized coding-agent prompt below.
```

It then includes the rendered prompt. It does not emit the notice during ordinary conversations without a reusable product finding.

Runtime activation updates the installed skill symlink immediately. A new agent session reads the new instructions normally; an already-running session that loaded the previous skill may need to reread it or start a new session before the updated completion behavior is reliable.
