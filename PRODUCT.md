# MegaBrain Product

## Thesis

MegaBrain is a private, user-owned personal context service for AI agents: teach one authorized agent and every authorized agent can retrieve the current, task-relevant context.

The target user works across multiple agent harnesses or models and wants durable context without binding it to one vendor. Useful examples include a home address used for routing, a corrected writing preference, or the location of a project document. Credentials are represented only by external references; MegaBrain never acts as a secret manager.

## Principles

1. The user is central; agents are replaceable clients.
2. Teach once, use everywhere.
3. Return task-specific context, not memory dumps.
4. Preserve provenance and correction history.
5. Keep data private by default.
6. Store secret references, never secret values.
7. Use an agent-agnostic MCP and HTTP protocol.
8. Keep user data inspectable, exportable, correctable, and forgettable.
9. Audit writes, access decisions, denial, correction, and revocation.
10. Add complexity only when an acceptance test requires it.

## V0 Scope And Acceptance

V0 proves that two independently authenticated clients can claim separately approved Brainlinks, share a confirmed private fact over HTTP, observe an atomic correction, and lose access immediately after revocation. It includes five MCP operations, an HTTP service, PostgreSQL migrations, a local administrator CLI, scoped resource references, portable export, and value-free audits.

Acceptance is the live-boundary test in `tests/cross-agent/portability.test.ts`, plus permission, replay, secret rejection, and current-fact tests.

## Non-goals

V0 is not a notes app, dashboard, knowledge graph, generic RAG system, chatbot, hosted relay, billing system, document ingestion service, secret retrieval system, or autonomous memory process. It performs no embeddings, vector search, server-side LLM extraction, personality simulation, or provider-specific agent adaptation.

## Future Hypotheses, Not Commitments

- Human approval may move to a web or messaging interface without changing Brainlink semantics.
- Credential rotation, rate limiting, hard deletion workflows, and stronger encrypted storage may be required for hosted use.
- Better deterministic matching or semantic retrieval may be justified by measured retrieval failures.
- Multi-owner tenancy may be useful after the single-owner security model is proven.
