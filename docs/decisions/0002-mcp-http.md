# ADR 0002: MCP Plus HTTP Boundary

**Decision:** Keep Fastify HTTP as the authorization boundary and implement the five MCP tools as an HTTP-forwarding stdio client.

All harnesses receive the same authentication, scopes, structured errors, revocation, and audit behavior. Provider adapters remain outside the core.
