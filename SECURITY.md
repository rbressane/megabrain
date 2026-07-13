# Security Policy

MegaBrain V0 is experimental and should be run only in a trusted local environment. Do not submit production credentials or real regulated data while evaluating it.

Report a vulnerability privately to the repository owner. Do not open a public issue containing personal data, tokens, or exploit details.

## Boundaries

- Brainlinks contain 256 bits of randomness, expire, are single-use, are stored only as hashes, and create pending agents with no data access.
- Agent credentials are shown once, stored only as SHA-256 hashes, compared in constant time, carried in authorization headers, and checked for revocation on every operation.
- Administrator approval selects explicit scopes. New agents receive no wildcard authority.
- Sensitivity filtering happens before fact or resource values leave the server.
- Corrections create a replacement and supersede the prior fact in one transaction. Forgetting tombstones a record.
- Common credential, private-key, token, and card patterns are rejected from ordinary facts. Secret resources contain locators only and are never dereferenced.
- Fastify does not log request bodies; authorization headers are not included in application audit metadata. Audits use record IDs, classifications, outcomes, and reason codes.
- Export excludes every stored credential, claim-secret, and invitation hash.

PostgreSQL and the deployment environment provide storage encryption in V0. MegaBrain does not implement or claim application-level encryption at rest.

## Operational Requirements

Use TLS outside loopback, bind only to trusted interfaces, restrict database access, keep `.env` and credentials out of Git, use a secret manager for agent credentials, grant minimal scopes, review audits, and revoke unexpected agents immediately. Run `npm run secret-scan` before committing.

Known threats and limitations are detailed in [docs/threat-model.md](docs/threat-model.md).
