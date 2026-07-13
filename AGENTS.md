# Agent Instructions

Build the smallest secure server that proves cross-harness context portability. Do not add semantic search, graphs, autonomous enrichment, a dashboard, or generalized knowledge management until a failing acceptance test demonstrates the need.

## Commands

- Install: `npm install`
- Database: `docker compose up -d && npm run db:migrate`
- Develop: `npm run dev`
- Verify: `npm run verify`
- Acceptance: `npm run test:cross-agent`
- Secret scan: `npm run secret-scan`

## Conventions

Use strict TypeScript, Zod at external boundaries, Drizzle for database access, structured `AppError` codes, and append-oriented audit events. Keep the HTTP service as the core boundary; MCP forwards to HTTP. Add migrations with schema changes and deterministic tests with synthetic data.

## Security Boundaries

Never store or log raw Brainlink tokens, claim secrets, agent credentials, authorization headers, or secret values. Agent operations require authentication and explicit scopes. Apply sensitivity filters before serialization. Corrections must remain transactional and preserve history. Secret references may be returned only as locators and metadata; never dereference them. Do not weaken revocation, replay, export, or audit guarantees for convenience.

Before finishing, run formatting, lint, type checking, all test layers, build, migration from a clean PostgreSQL database, the README flow, and the secret scan. Inspect tracked files for private data and report any verification that could not run.
