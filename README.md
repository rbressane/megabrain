# MegaBrain

MegaBrain lets a user teach one authorized agent a durable fact and retrieve the current fact from every other authorized agent.

**Status:** experimental V0. It is a local proof of secure cross-agent context portability, not a hosted service.

## Prerequisites

- Node.js 22+
- npm
- Docker with Compose and `jq` for the demonstration

## Setup

```bash
npm install
cp .env.example .env
docker compose up -d
npm run db:migrate
npm run cli -- init --display-name "Taylor Example"
```

Run the server in another terminal:

```bash
npm run dev
```

The migration files are committed under `src/db/migrations`. Apply them with `npm run db:migrate`. Generate a reviewed migration after changing the Drizzle schema with `npm run db:generate`.

## Complete Local Demonstration

The following uses the administrator CLI for invitations, approval, and revocation. Both agents claim, exchange credentials, and access facts only over HTTP. The local HTTP helper reads JSON from stdin and bearer credentials from the environment so raw tokens do not enter process arguments.

```bash
SCOPES_A='context:read:private,facts:write,facts:correct'
SCOPES_B='context:read:private'

LINK_A=$(npm run --silent cli -- invite create --expires-in 15m | jq -r .brainlink)
CLAIM_A=$(jq -n --arg token "${LINK_A##*token=}" --arg scopes "$SCOPES_A" \
  '{token:$token,displayName:"Agent A",harnessType:"local-http-a",requestedScopes:($scopes|split(","))}' \
  | npm run --silent http -- /v1/brainlinks/claim)
REQUEST_A=$(jq -r .requestId <<<"$CLAIM_A")
npm run --silent cli -- requests approve "$REQUEST_A" --scopes "$SCOPES_A"
TOKEN_A=$(jq -c '{requestId,claimSecret}' <<<"$CLAIM_A" \
  | npm run --silent http -- /v1/brainlinks/exchange | jq -r .credential)

LINK_B=$(npm run --silent cli -- invite create --expires-in 15m | jq -r .brainlink)
CLAIM_B=$(jq -n --arg token "${LINK_B##*token=}" --arg scopes "$SCOPES_B" \
  '{token:$token,displayName:"Agent B",harnessType:"local-http-b",requestedScopes:($scopes|split(","))}' \
  | npm run --silent http -- /v1/brainlinks/claim)
REQUEST_B=$(jq -r .requestId <<<"$CLAIM_B")
npm run --silent cli -- requests approve "$REQUEST_B" --scopes "$SCOPES_B"
TOKEN_B=$(jq -c '{requestId,claimSecret}' <<<"$CLAIM_B" \
  | npm run --silent http -- /v1/brainlinks/exchange | jq -r .credential)

FACT_ID=$(printf '%s' '{"subject":"person","predicate":"home_address","value":"18 Example Avenue, Sampletown","confidence":"confirmed","sensitivity":"private","source":{"type":"direct-statement","reference":"synthetic demo statement"}}' \
  | MEGABRAIN_AGENT_TOKEN="$TOKEN_A" npm run --silent http -- /v1/facts | jq -r .id)

printf '%s' '{"task":"Calculate the distance between my home and the supermarket."}' \
  | MEGABRAIN_AGENT_TOKEN="$TOKEN_B" npm run --silent http -- /v1/context | jq

jq -n --arg id "$FACT_ID" '{previousFactId:$id,replacementValue:"42 Testing Road, Sampletown",source:{type:"direct-statement",reference:"synthetic demo correction"},reason:"address changed"}' \
  | MEGABRAIN_AGENT_TOKEN="$TOKEN_A" npm run --silent http -- /v1/facts/correct | jq

printf '%s' '{"task":"Calculate the distance between my home and the supermarket."}' \
  | MEGABRAIN_AGENT_TOKEN="$TOKEN_B" npm run --silent http -- /v1/context | jq

npm run --silent cli -- agents revoke "$REQUEST_B"
printf '%s' '{"task":"Calculate the distance between my home and the supermarket."}' \
  | MEGABRAIN_AGENT_TOKEN="$TOKEN_B" npm run --silent http -- /v1/context | jq || true

unset LINK_A CLAIM_A TOKEN_A LINK_B CLAIM_B TOKEN_B
```

Inspect or export user-owned records:

```bash
npm run cli -- inspect facts
npm run cli -- inspect audit
npm run cli -- export
```

Exports omit invitation hashes, claim-secret hashes, credential hashes, and all raw credentials.

## MCP Configuration

Start the HTTP server first. Configure an MCP client with an approved agent credential supplied from a secret-bearing environment, never from a committed file:

```json
{
  "mcpServers": {
    "megabrain": {
      "command": "npm",
      "args": ["run", "--silent", "mcp"],
      "cwd": "/absolute/path/to/megabrain",
      "env": {
        "MEGABRAIN_BASE_URL": "http://127.0.0.1:3210",
        "MEGABRAIN_AGENT_TOKEN": "<approved-agent-credential>"
      }
    }
  }
}
```

The MCP surface has exactly five tools: `get_context`, `remember`, `correct`, `locate`, and `forget`.

## Verification

```bash
npm run format:check
npm run lint
npm run typecheck
npm run test:unit
npm run test:integration
npm run test:cross-agent
npm run build
npm run secret-scan
```

## Security Warning

MegaBrain stores private personal context. Run it only on a trusted machine and network, use deployment-level TLS and encrypted storage outside local development, keep agent credentials in a secret manager, and grant the narrowest scopes. MegaBrain rejects common secret-value patterns from facts but that defensive check is not exhaustive. See [SECURITY.md](SECURITY.md) and [docs/threat-model.md](docs/threat-model.md).

## Current Limitations

V0 is single-owner per installation, uses deterministic lexical retrieval, has no encryption layer of its own, and relies on PostgreSQL plus deployment controls for encryption at rest. Brainlink approval is CLI-only. Forgetting is a tombstone, not regulatory erasure. There is no rate limiter, hosted relay, dashboard, key rotation, semantic search, or automatic fact extraction.
