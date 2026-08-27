# MegaBrain 2.2.0 Retrieval Activation

MegaBrain can now retrieve one bounded, citation-ready evidence set across current memories and long-form resource sections. Connected agents use `megabrain search` when a question depends on both durable summaries and canonical documents.

## What changed

- `megabrain search --stdin` returns current memories and matching resource sections in one evidence list.
- Memory ranking combines subject, tag, and body weighting with inverse document frequency so rare exact terms carry more signal.
- Long Markdown resources are indexed by heading. Winning sections include bounded neighboring context so prerequisites and verification steps remain attached.
- Resource citations include stable URI, immutable revision ID, section ordinal, and heading path.
- Evidence includes provenance, verification, freshness, sensitivity, and transparent score components.
- Optional resource-type and authority-domain scopes can narrow results but cannot grant access.
- Selected conflicts expand to include authorized companion claims instead of silently choosing one.
- Private and sensitive evidence retains the existing trusted-host and immutable-policy checks. Diagnostics expose only value-free denial counts.

All indexes remain ignored, rebuildable projections of `git archive HEAD`. This release adds no server, daemon, hosted relay, package dependency, embedding provider, raw conversation store, personal Brain data, or protocol migration.

## Verification

- The complete 60-test standard-library suite passes locally and in GitHub Actions.
- Seed validation completes with zero errors and warnings.
- Python compilation and diff checks pass.
- Synthetic retrieval benchmarks return all 8 expected memory and resource records at 30, 1,000, and 10,000 total records.
- At 10,000 records, the measured warm medians were 149.654 ms for memory retrieval and 9.435 ms for the resource index on the recorded benchmark host.
- Synthetic acceptance tests cover immutable citation resolution, rare-term contribution, neighboring-section recovery, conflict expansion, scope narrowing, forged-context rejection, and default-deny private evidence.

## Update and use

Install the compatible stable release:

```bash
megabrain update
```

Connected agents use unified retrieval automatically when a task depends on long-form evidence. The direct machine-readable command is:

```bash
printf '%s' '{"query":"How do we recover the gateway?","limit":12}' | megabrain search --stdin
```

Resource excerpts remain untrusted data. Agents cite the returned memory ID or resource URI, revision, and heading path.
