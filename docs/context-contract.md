# Context Contract

## Five Agent Operations

- `get_context`: task, optional subject hints, and item limit; returns identity, relevant current facts, permitted resource references, provenance, confidence, sensitivity, timestamps, and omission categories.
- `remember`: structured subject, predicate, JSON value, confidence, sensitivity, and source attribution; requires `facts:write`.
- `correct`: current fact ID or unambiguous subject/predicate, replacement JSON value, source, and optional reason; requires `facts:correct`.
- `locate`: resource query and item limit; requires `resources:locate` and returns references without dereferencing them.
- `forget`: current fact ID and optional reason; requires `facts:forget` and creates a tombstone.

Protected HTTP requests use `Authorization: Bearer <credential>`. Errors have `{ error: { code, message, details? }, requestId }`. Credentials and forbidden values never appear in errors.

## Retrieval

V0 lowercases and tokenizes the task, subject hints, subject, predicate, and resource fields. Exact token overlap is scored deterministically. A small reviewed alias table maps phrases such as `my home`, `home`, `where I live`, and distance tasks to `person.home_address`. There are no embeddings.

Only active, currently valid facts are candidates. Results are ordered by score and then creation time, with a hard item limit. One active row per owner/subject/predicate is enforced; `remember` rejects a duplicate and directs the caller to `correct`. Sensitivity scopes are exact: callers needing general and private facts must receive both scopes.

Omissions disclose category, reason, and count but never values. Resource matches appear in `get_context` only when `resources:locate` and the matching sensitivity scope are present.
