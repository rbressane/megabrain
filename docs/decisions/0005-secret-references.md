# ADR 0005: Secret References

**Decision:** Store only external locators and classification metadata for secrets, never secret values.

MegaBrain is a context service rather than a secret manager. Locators can identify where a credential lives but are never dereferenced by the service.
