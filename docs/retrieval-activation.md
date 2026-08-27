# Retrieval and Activation

MegaBrain keeps canonical knowledge in immutable Markdown and uses ignored SQLite indexes only as disposable projections of a committed Git snapshot. Retrieval may improve without changing that authority model.

## Unified evidence

`megabrain search --stdin` accepts a natural-language `query`, an optional result `limit`, and optional `resource_type` or `authority_domain` scopes. It returns one bounded evidence list containing:

- current memory summaries with immutable memory IDs;
- current resource sections with stable resource URI, revision ID, section ordinal, and heading path;
- source provenance, sensitivity, verification, and freshness metadata;
- transparent relevance scores and score components;
- adjacent Markdown sections around each resource match;
- explicit memory and resource conflicts.

Resource bodies, headings, and adjacent context remain `untrusted_data`. Embedded instructions never execute.

## Ranking

Memory retrieval combines subject, tag, and body overlap with inverse document frequency so rare exact terms carry more signal than common vocabulary. Resource-section retrieval combines title, heading, body, rare-term, exact-phrase, and query-coverage signals. Results from both evidence types are normalized and fused with deterministic source diversity.

This is lexical hybrid retrieval, not semantic embedding search. It improves exact technical terms and long-document activation without adding a model, service, package dependency, or external disclosure path.

## Section context

The resource index splits Markdown at ATX headings. A winning section returns its own bounded excerpt plus the preceding and following sections, capped to a bounded context size. This preserves prerequisites and verification steps that chunk-only retrieval can separate.

The index schema and section boundaries are not canonical. A runtime can delete and rebuild the index from `git archive HEAD` without changing Brain history.

## Access and conflicts

General evidence follows normal local retrieval. Private and sensitive evidence requires the same trusted host context and immutable access policy used by memory context and resource reads. Filtering happens before evidence leaves the helper. Diagnostic output reports value-free denial counts.

A result that intersects a current conflict expands to include authorized companion claims, even when that exceeds the requested limit within the fixed conflict-expansion budget. Retrieval never silently chooses one conflicting claim.

Scopes only reduce the candidate set. A project, resource type, or authority domain cannot grant access.

## Design source and boundary

The evidence pipeline is informed by Cerebras Knowledge's public description of source-aware retrieval, rare-term ranking, rank fusion, context expansion, scoped projects, and citation-backed synthesis:

- https://www.cerebras.ai/blog/how-we-built-our-knowledge-base

MegaBrain does not copy Cerebras's centralized Postgres, pgvector, hosted service, real-time ingestion, mandatory LLM processing, or raw conversation storage. Product repositories, task systems, mail, calendars, and infrastructure remain authoritative for their live domains. MegaBrain stores approved durable knowledge and pointers under its existing review and privacy boundaries.

## Evaluation requirements

Retrieval changes must use synthetic data and measure more than latency:

- recall at a fixed budget;
- first-relevant rank;
- rare exact-term ranking;
- long-document section and neighbor recovery;
- citation resolution to committed immutable records;
- complete conflict expansion;
- zero protected-content leakage without authorization;
- cold and warm performance at representative corpus sizes.

An embedding or LLM reranking experiment must remain optional and disposable until it demonstrates a material measured gain without weakening privacy, offline operation, deterministic fallback, or the standard-library runtime.
