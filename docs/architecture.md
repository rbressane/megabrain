# Architecture

MegaBrain V0 is one Fastify process backed by PostgreSQL 16. Zod contracts validate HTTP and MCP inputs. Drizzle provides typed database access and reviewed SQL migrations.

The administrator CLI connects directly to the local database for owner initialization, Brainlink creation, approval, denial, inspection, revocation, and export. Agent clients cross the HTTP boundary. The stdio MCP server exposes exactly five tools and forwards each call to the authenticated HTTP equivalent, keeping authorization and auditing in one core path.

Brainlink claim creates a pending agent and a one-time claim secret. Approval selects scopes. Credential exchange generates the long-lived credential only once, returns it to the claimant, and stores only its hash. Every protected request authenticates, checks live agent status, checks operation scope, filters sensitivity, and writes value-free audit events.

Facts are structured JSON records. One active value per owner/subject/predicate avoids ambiguous single-valued state. Corrections supersede the active row and insert its replacement in one transaction. Context compilation scans only current rows and applies deterministic token and alias scoring.
