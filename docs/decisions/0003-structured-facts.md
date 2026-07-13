# ADR 0003: Structured Facts

**Decision:** Agents submit explicit subject, predicate, typed JSON value, sensitivity, confidence, and source fields.

The server validates and stores structure but performs no LLM extraction. This keeps writes deterministic and avoids hidden interpretation of private statements.
